//! Ausgabe an den Daemon: typisierte Nachrichten, geschrieben von genau einem Thread.
//!
//! Früher schrieb jeder Thread selbst auf stdout, auch der Frame-Callback im Parser. Hing der
//! Daemon, blieb der Parser stehen und der Paketkanal lief voll. Jetzt legen alle nur in eine
//! Warteschlange; der Schreib-Thread allein wartet auf den Daemon.
//!
//! Zwei Arten von Nachrichten:
//! - Zustände (`dps`, `dps_data`, `status`, `plugin_character`): nur der neueste zählt. Steht ein
//!   älterer derselben Art noch in der Warteschlange, wird er an seinem Platz ersetzt.
//! - Ereignisse (alles andere): kommen in Reihenfolge an. Ist die Warteschlange voll, gehen sie im
//!   Live-Betrieb verloren (gezählt und gemeldet), statt den Mitschnitt aufzuhalten.
//!
//! Im Replay (`Policy::Lossless`) geht nichts verloren und nichts wird ersetzt: Wer schreibt, wartet,
//! bis Platz ist. So bleibt die Ausgabe Zeile für Zeile gleich (Goldtest).
//!
//! Zeilenformat `dps_data`: genau `{"type":"dps_data","data":…}`. Der Daemon schneidet `data` als
//! Text heraus, ohne die bis zu 100 KB zu parsen (capture.py).

use std::collections::VecDeque;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use a2tools_dps_meter_lib::entity::dps_data::DpsData;
use parking_lot::{Condvar, Mutex};
use serde::Serialize;
use serde_json::Value;
use tracing::warn;

use crate::view::View;

/// So viele Zeilen warten höchstens auf den Daemon (Ereignisse; Zustände ersetzen sich)
const QUEUE_MAX: usize = 4096;
/// Verlorene Ereignisse melden: beim ersten und dann jedes Mal nach so vielen
const DROP_REPORT_EVERY: u64 = 1000;

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Message<'a> {
    Hello(&'a Hello),
    Dps {
        view: &'a View,
    },
    DpsData {
        data: &'a DpsData,
    },
    Status(&'a Status),
    FightsSaved {
        ids: &'a [String],
    },
    Reply(&'a Reply),
    Bye,
    PluginFrame {
        plugin: &'a str,
        event: String,
        data: &'a Value,
        immediate: bool,
        at: i64,
    },
    PluginCharacter {
        data: &'a Value,
    },
    PluginFeed {
        event: &'a str,
        at: i64,
        data: &'a Value,
    },
    /// Rohes Spielpaket für ein abonniertes Opcode (frames.rs): `op` als Zahl, `data` als Hex
    Frame {
        op: u16,
        data: String,
        at: i64,
    },
}

impl Message<'_> {
    /// Art eines Zustands; None = Ereignis.
    fn state_key(&self) -> Option<&'static str> {
        match self {
            Message::Dps { .. } => Some("dps"),
            Message::DpsData { .. } => Some("dps_data"),
            Message::Status(_) => Some("status"),
            Message::PluginCharacter { .. } => Some("plugin_character"),
            _ => None,
        }
    }
}

/// Gruß beim Start: was läuft und was der Daemon voraussetzen darf.
#[derive(Serialize, Default)]
pub struct Hello {
    pub version: &'static str,
    pub parser: String,
    pub history_dir: PathBuf,
    /// "party" = Zeilen tragen das Gruppen-Flag (view.rs), "dps_data" = volle Daten als eigene Zeile
    pub features: &'static [&'static str],
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pcap: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cap_net_raw: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub replay: Option<PathBuf>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub packets: Option<usize>,
}

/// Stand des Mitschnitts, gemeldet bei jeder Änderung.
#[derive(Serialize, Default, Clone, PartialEq)]
pub struct Status {
    pub capturing: bool,
    pub game: bool,
    pub port: Option<u16>,
    pub device: Option<String>,
    pub ping: Option<i32>,
    pub dungeon: i32,
    pub local_id: Option<i64>,
    pub suspended: bool,
}

/// Antwort auf einen Befehl: `result` bei Erfolg (auch null), sonst `error`.
#[derive(Serialize)]
pub struct Reply {
    pub id: Value,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

impl Reply {
    pub fn new(id: Value, outcome: Result<Value, String>) -> Self {
        match outcome {
            Ok(result) => Self { id, ok: true, result: Some(result), error: None },
            Err(error) => Self { id, ok: false, result: None, error: Some(error) },
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Policy {
    /// Mitschnitt: nie warten, Zustände ersetzen, Ereignisse bei voller Warteschlange verwerfen
    Live,
    /// Replay: jede Zeile, notfalls warten
    Lossless,
}

struct Line {
    key: Option<&'static str>,
    text: String,
}

#[derive(Default)]
struct Queue {
    lines: VecDeque<Line>,
    writing: bool, // der Schreib-Thread hat Zeilen herausgenommen und schreibt sie gerade
    dropped: u64,
}

struct Shared {
    queue: Mutex<Queue>,
    changed: Condvar,
    policy: Policy,
}

/// Griff auf die Warteschlange; billig zu klonen, alle Klone teilen denselben Schreib-Thread.
#[derive(Clone)]
pub struct Out {
    shared: Arc<Shared>,
}

impl Out {
    /// Startet den Schreib-Thread auf `writer` (im Programm stdout, in Tests ein Puffer).
    pub fn spawn(writer: impl Write + Send + 'static, policy: Policy) -> Self {
        let shared = Arc::new(Shared { queue: Mutex::default(), changed: Condvar::new(), policy });
        let worker = shared.clone();
        std::thread::Builder::new()
            .name("ausgabe".into())
            .spawn(move || write_loop(&worker, writer))
            .expect("Schreib-Thread");
        Self { shared }
    }

    pub fn send(&self, message: &Message) {
        match serde_json::to_string(message) {
            Ok(text) => self.push(Line { key: message.state_key(), text }),
            Err(e) => warn!("Nachricht nicht serialisierbar: {e}"),
        }
    }

    fn push(&self, line: Line) {
        let mut q = self.shared.queue.lock();
        if self.shared.policy == Policy::Lossless {
            while q.lines.len() >= QUEUE_MAX {
                self.shared.changed.wait(&mut q);
            }
        } else if let Some(old) = line.key.and_then(|key| q.lines.iter_mut().find(|l| l.key == Some(key))) {
            old.text = line.text;
            return;
        } else if line.key.is_none() && q.lines.len() >= QUEUE_MAX {
            q.dropped += 1;
            if q.dropped % DROP_REPORT_EVERY == 1 {
                warn!("Daemon liest nicht mit: {} Nachrichten verworfen", q.dropped);
            }
            return;
        }
        q.lines.push_back(line);
        self.shared.changed.notify_all();
    }

    /// Wartet, bis alles geschrieben ist (beim Beenden); false, wenn der Daemon nicht mehr liest.
    pub fn flush(&self, timeout: Duration) -> bool {
        let deadline = Instant::now() + timeout;
        let mut q = self.shared.queue.lock();
        while !q.lines.is_empty() || q.writing {
            if self.shared.changed.wait_until(&mut q, deadline).timed_out() {
                return false;
            }
        }
        true
    }
}

/// Nimmt alles, was wartet, und schreibt es in einem Rutsch; nur hier wird auf den Daemon gewartet.
fn write_loop(shared: &Shared, mut writer: impl Write) {
    loop {
        let batch: Vec<Line> = {
            let mut q = shared.queue.lock();
            q.writing = false;
            shared.changed.notify_all();
            while q.lines.is_empty() {
                shared.changed.wait(&mut q);
            }
            q.writing = true;
            q.lines.drain(..).collect()
        };
        shared.changed.notify_all(); // Platz für Wartende im Replay
        let mut failed = false;
        for line in &batch {
            failed |= writeln!(writer, "{}", line.text).is_err();
        }
        failed |= writer.flush().is_err();
        if failed {
            return; // Daemon weg: nichts mehr zu tun, das Programm endet über stdin
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::mpsc;

    /// Ein Daemon, der nicht liest: jedes write wartet, bis der Test es freigibt.
    struct Stuck {
        release: mpsc::Receiver<()>,
        lines: Arc<Mutex<Vec<String>>>,
    }

    impl Write for Stuck {
        fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
            let _ = self.release.recv();
            self.lines.lock().push(String::from_utf8_lossy(buf).into_owned());
            Ok(buf.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    fn status(ping: i32) -> Status {
        Status { ping: Some(ping), ..Status::default() }
    }

    fn reply(n: i64) -> Reply {
        Reply::new(json!(n), Ok(Value::Null))
    }

    #[test]
    fn haengender_daemon_haelt_niemanden_auf() {
        let (release, rx) = mpsc::channel();
        let lines = Arc::new(Mutex::new(Vec::new()));
        let out = Out::spawn(Stuck { release: rx, lines: lines.clone() }, Policy::Live);
        let start = Instant::now();
        for n in 0..(QUEUE_MAX as i64 * 3) {
            out.send(&Message::Reply(&reply(n)));
            out.send(&Message::Status(&status(n as i32)));
        }
        assert!(start.elapsed() < Duration::from_secs(2), "send darf nicht warten");
        let q = out.shared.queue.lock();
        assert!(q.lines.len() <= QUEUE_MAX + 1, "Warteschlange bleibt begrenzt");
        assert!(q.dropped > 0);
        assert_eq!(q.lines.iter().filter(|l| l.key == Some("status")).count(), 1, "nur der neueste Status");
        drop(q);
        drop(release); // Daemon liest wieder
    }

    #[test]
    fn zustand_ersetzt_den_wartenden_an_seinem_platz() {
        let (release, rx) = mpsc::channel();
        let lines = Arc::new(Mutex::new(Vec::new()));
        let out = Out::spawn(Stuck { release: rx, lines: lines.clone() }, Policy::Live);
        out.send(&Message::Bye); // hängt im write fest
        std::thread::sleep(Duration::from_millis(50));
        out.send(&Message::Status(&status(1)));
        out.send(&Message::Reply(&reply(7)));
        out.send(&Message::Status(&status(2)));
        for _ in 0..8 {
            let _ = release.send(());
        }
        assert!(out.flush(Duration::from_secs(2)));
        let text: Vec<String> = lines.lock().iter().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
        assert_eq!(
            text,
            vec![
                r#"{"type":"bye"}"#.to_string(),
                serde_json::to_string(&Message::Status(&status(2))).unwrap(),
                r#"{"type":"reply","id":7,"ok":true,"result":null}"#.to_string(),
            ]
        );
    }

    #[test]
    fn replay_verliert_nichts() {
        let buffer = Arc::new(Mutex::new(Vec::<u8>::new()));
        struct Shared(Arc<Mutex<Vec<u8>>>);
        impl Write for Shared {
            fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
                self.0.lock().extend_from_slice(buf);
                Ok(buf.len())
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let out = Out::spawn(Shared(buffer.clone()), Policy::Lossless);
        for n in 0..(QUEUE_MAX * 2) {
            out.send(&Message::Status(&status(n as i32)));
        }
        assert!(out.flush(Duration::from_secs(5)));
        let text = String::from_utf8(buffer.lock().clone()).unwrap();
        assert_eq!(text.lines().count(), QUEUE_MAX * 2);
    }

    #[test]
    fn dps_data_beginnt_wie_dokumentiert() {
        let data = DpsData::new();
        let text = serde_json::to_string(&Message::DpsData { data: &data }).unwrap();
        assert!(text.starts_with(r#"{"type":"dps_data","data":{"#) && text.ends_with('}'));
    }
}
