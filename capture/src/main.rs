//! deckbar-capture: AION-2-Mitschnitt für die DeckBar.
//!
//! Setzt den Kern des A2Tools DPS Meter (GPL-3.0, Submodul `a2tools/`) ohne dessen Oberfläche
//! zusammen, so wie `app.rs` dort es tut: libpcap auf allen Interfaces → CaptureDispatcher
//! (Port-Erkennung, Reassembly, Parser) → DataStorage → DpsCalculator. Der Daemon startet das
//! Programm und spricht mit ihm über Zeilen-JSON:
//!
//!   stdout  {"type":"hello"|"dps"|"status"|"fights_saved"|"reply"|"bye", …}
//!   stdin   {"id":1,"cmd":"reset"|"target_mode"|"details"|"buffs"|"context"|"history"|"fight"|
//!            "suspend"|"language"|"save"|"snapshot"|"view", …}
//!   stderr  Log (RUST_LOG, Standard: warn, für dieses Programm info)
//!
//! `dps` kommt höchstens alle `--interval-ms` und nur bei Änderung, `status` bei Änderung. `dps`
//! enthält `view` (Zeilen wie im Stream-Overlay, siehe view.rs) und nach `{"cmd":"view","full":true}`
//! zusätzlich `data` (DpsData des Meters mit Skill-Aufschlüsselung, bis ~100 KB).
//! Kampf-History: alle 30 s, vor jedem Zurücksetzen der Kampfdaten (Zonenwechsel …) und beim
//! Beenden, als `<history-dir>/history/<id>.json` im Format des Meters.
//!
//! Rechte: Mitschneiden braucht `cap_net_raw` (`sudo setcap cap_net_raw=ep deckbar-capture`),
//! root nicht. Pakete wertet der Kern nur aus, solange AION2.exe läuft.

use std::collections::HashSet;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Weak};
use std::time::Duration;

use a2tools_dps_meter_lib::capture::captured_payload::CapturedPayload;
use a2tools_dps_meter_lib::capture::combat_port_detector::CombatPortDetector;
use a2tools_dps_meter_lib::capture::packet_accumulator::PacketAccumulator;
use a2tools_dps_meter_lib::capture::pcap_capturer::PcapCapturer;
use a2tools_dps_meter_lib::capture::stream_processor::StreamProcessor;
use a2tools_dps_meter_lib::combat::capture_dispatcher::CaptureDispatcher;
use a2tools_dps_meter_lib::combat::data_storage::DataStorage;
use a2tools_dps_meter_lib::combat::dps_calculator::DpsCalculator;
use a2tools_dps_meter_lib::combat::ping_tracker::PingTracker;
use a2tools_dps_meter_lib::history::fight_history::FightHistoryManager;
use a2tools_dps_meter_lib::i18n::lookup::{self, NpcLookup, SkillLookup};
use a2tools_dps_meter_lib::{capture, logging, platform, rederive, share};
use parking_lot::Mutex;
use serde_json::{Value, json};
use tokio::io::AsyncBufReadExt;
use tokio::sync::mpsc;
use tracing::{info, warn};

mod view;

const HISTORY_EVERY: Duration = Duration::from_secs(30);
const STATUS_EVERY: Duration = Duration::from_secs(2);

struct Args {
    data_dir: PathBuf,
    history_dir: PathBuf,
    lang: String,
    device: Option<String>,
    interval: Duration,
    replay: Option<PathBuf>,
    realtime: bool,
    save_packets: Option<PathBuf>,
}

fn usage() -> ! {
    eprintln!(
        "deckbar-capture [--data DIR] [--history-dir DIR] [--lang en] [--device IFACE]\n\
         \x20               [--interval-ms 500] [--save-packets DIR] [--replay packets.txt [--realtime]]"
    );
    std::process::exit(2);
}

fn parse_args() -> Args {
    let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    let data_home = std::env::var_os("XDG_DATA_HOME").map(PathBuf::from).unwrap_or_else(|| home.join(".local/share"));
    let mut a = Args {
        data_dir: PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/a2tools/src/data")),
        history_dir: data_home.join("deckbar/aion2"),
        lang: "en".into(),
        device: None,
        interval: Duration::from_millis(500),
        replay: None,
        realtime: false,
        save_packets: None,
    };
    let mut it = std::env::args().skip(1);
    while let Some(arg) = it.next() {
        let mut val = || it.next().unwrap_or_else(|| usage());
        match arg.as_str() {
            "--data" => a.data_dir = val().into(),
            "--history-dir" => a.history_dir = val().into(),
            "--lang" => a.lang = val(),
            "--device" => a.device = Some(val()),
            "--interval-ms" => a.interval = Duration::from_millis(val().parse().unwrap_or_else(|_| usage())),
            "--replay" => a.replay = Some(val().into()),
            "--realtime" => a.realtime = true,
            "--save-packets" => a.save_packets = Some(val().into()),
            _ => usage(),
        }
    }
    a
}

/// Eine JSON-Zeile auf stdout, von jedem Thread aus.
fn emit(v: &Value) {
    emit_line(&v.to_string());
}

fn emit_line(line: &str) {
    let mut out = std::io::stdout().lock();
    let _ = writeln!(out, "{line}");
    let _ = out.flush();
}

struct Core {
    storage: Arc<DataStorage>,
    calc: Mutex<DpsCalculator>,
    skills: Arc<SkillLookup>,
    npcs: Arc<NpcLookup>,
    ping: Arc<PingTracker>,
    history: FightHistoryManager,
    save_lock: Mutex<()>,
    data_dir: PathBuf,
    dot_ids: HashSet<i32>,
    suspended: Arc<AtomicBool>,
    view: Mutex<(view::Options, bool)>, // Zeilen-Optionen, volle DpsData mitschicken
}

impl Core {
    fn new(args: &Args, ping: Arc<PingTracker>) -> Arc<Self> {
        let skills = SkillLookup::new();
        let npcs = NpcLookup::new();
        lookup::load_language(&skills, &npcs, &args.data_dir, &args.lang);
        let (skills, npcs) = (Arc::new(skills), Arc::new(npcs));

        let mut dot_ids = HashSet::new();
        match std::fs::read_to_string(args.data_dir.join("dot_skill_ids.json")) {
            Ok(text) => dot_ids.extend(serde_json::from_str::<Vec<i32>>(&text).unwrap_or_default()),
            Err(e) => warn!("dot_skill_ids.json fehlt in {}: {e}", args.data_dir.display()),
        }
        let storage = Arc::new(DataStorage::new());
        if let Ok(text) = std::fs::read_to_string(args.data_dir.join("abnormals.json")) {
            storage.set_abnormal_stack_limits(capture::abnormal::stack_limits(&text));
        }
        let _ = std::fs::create_dir_all(&args.history_dir);
        let core = Arc::new(Core {
            calc: Mutex::new(DpsCalculator::new(storage.clone(), skills.clone(), npcs.clone(), ping.clone())),
            storage,
            skills,
            npcs,
            ping,
            history: FightHistoryManager::new(args.history_dir.clone()),
            save_lock: Mutex::new(()),
            data_dir: args.data_dir.clone(),
            dot_ids,
            suspended: Arc::new(AtomicBool::new(false)),
            view: Mutex::new((view::Options::default(), false)),
        });
        // Vor jedem Zurücksetzen der Kampfdaten (Zonenwechsel, Gruppenende) speichern, sonst
        // ginge alles seit dem letzten 30-s-Speichern verloren (wie im Meter, dort Issue #19).
        let weak: Weak<Core> = Arc::downgrade(&core);
        core.storage.set_before_reset(move || {
            if let Some(core) = weak.upgrade() {
                core.save(true);
            }
        });
        core
    }

    /// Ein frischer Rechner auf denselben Daten, für Detailabfragen neben dem Live-Tick.
    fn reader(&self) -> DpsCalculator {
        DpsCalculator::new(self.storage.clone(), self.skills.clone(), self.npcs.clone(), self.ping.clone())
    }

    /// Bosskämpfe in die History. `force` auch laufende Kämpfe (vor Reset und beim Beenden).
    fn save(&self, force: bool) {
        let _saving = self.save_lock.lock();
        if self.storage.damage_generation() <= 0 {
            return;
        }
        let records = if force {
            self.calc.lock().snapshot_boss_fights_force()
        } else {
            match self.calc.try_lock() {
                Some(mut calc) => calc.snapshot_boss_fights(),
                None => return, // Tick rechnet gerade, nächstes Mal
            }
        };
        let mut ids = Vec::new();
        for record in &records {
            match self.history.save_fight(record) {
                Ok(()) => ids.push(record.id.clone()),
                Err(e) => warn!("Kampf {} nicht gespeichert: {e}", record.id),
            }
        }
        if !ids.is_empty() {
            emit(&json!({"type": "fights_saved", "ids": ids}));
        }
    }

    fn reset(&self) {
        self.save(true);
        self.calc.lock().restart_target_selection(true);
        self.storage.forget_guessed_nicknames();
        self.storage.hide_party_placeholders();
    }

    fn command(&self, cmd: &Value) -> Result<Value, String> {
        let str_arg = |k: &str| cmd.get(k).and_then(Value::as_str).ok_or(format!("{k} fehlt"));
        let target = || {
            cmd.get("target_id").and_then(Value::as_i64).map(|v| v as i32).ok_or("target_id fehlt".to_string())
        };
        let to_value = |v: Result<Value, serde_json::Error>| v.map_err(|e| e.to_string());
        match cmd.get("cmd").and_then(Value::as_str).unwrap_or("") {
            "snapshot" => to_value(serde_json::to_value(self.calc.lock().get_dps())),
            "reset" => {
                self.reset();
                Ok(Value::Null)
            }
            "save" => {
                self.save(true);
                Ok(Value::Null)
            }
            "target_mode" => {
                self.calc.lock().set_target_selection_mode(str_arg("mode")?);
                Ok(Value::Null)
            }
            "details" => {
                let actors: Option<Vec<i32>> = cmd.get("actor_ids").and_then(|v| serde_json::from_value(v.clone()).ok());
                let reader = self.reader();
                let res = if cmd.get("summary").and_then(Value::as_bool).unwrap_or(false) {
                    reader.get_hover_details(target()?, actors.as_deref())
                } else {
                    reader.get_target_details(target()?, actors.as_deref())
                };
                to_value(serde_json::to_value(res))
            }
            "buffs" => to_value(serde_json::to_value(self.reader().live_fight_buffs(target()?))),
            "context" => to_value(serde_json::to_value(self.reader().get_details_context())),
            "history" => to_value(serde_json::to_value(self.history.list_fights())),
            "fight" => to_value(serde_json::to_value(self.history.load_fight(str_arg("fight_id")?)?)),
            "suspend" => {
                let on = cmd.get("on").and_then(Value::as_bool).unwrap_or(true);
                self.suspended.store(on, Ordering::SeqCst);
                Ok(Value::Null)
            }
            "view" => {
                let mut v = self.view.lock();
                if let Some(n) = cmd.get("limit").and_then(Value::as_u64) {
                    v.0.limit = n.clamp(1, 24) as usize;
                }
                if let Some(b) = cmd.get("pin_you").and_then(Value::as_bool) {
                    v.0.pin_you = b;
                }
                if let Some(b) = cmd.get("full").and_then(Value::as_bool) {
                    v.1 = b;
                }
                Ok(Value::Null)
            }
            "language" => {
                lookup::load_language(&self.skills, &self.npcs, &self.data_dir, str_arg("lang")?);
                Ok(Value::Null)
            }
            other => Err(format!("unbekannter Befehl {other:?}")),
        }
    }
}

/// DPS-Zeile, wenn sie sich geändert hat.
fn tick(core: &Core, last: &mut String) {
    let dps = core.calc.lock().get_dps();
    let (opts, full) = core.view.lock().clone();
    let Ok(view) = serde_json::to_string(&view::build(&dps, &opts)) else { return };
    let line = match full.then(|| serde_json::to_string(&dps)) {
        Some(Ok(data)) => format!(r#"{{"type":"dps","view":{view},"data":{data}}}"#),
        _ => format!(r#"{{"type":"dps","view":{view}}}"#),
    };
    if line != *last {
        emit_line(&line);
        *last = line;
    }
}

fn status(core: &Core, ports: Option<&CombatPortDetector>, capturing: bool) -> Value {
    json!({
        "type": "status",
        "capturing": capturing,
        "game": platform::window_detector::find_aion2_window(),
        "port": ports.and_then(|p| p.current_port()),
        "device": ports.and_then(|p| p.current_device()),
        "ping": core.ping.current_ping_ms(),
        "dungeon": core.storage.current_dungeon_id(),
        "local_id": core.storage.local_player_id(),
        "suspended": core.suspended.load(Ordering::SeqCst),
    })
}

/// Befehle von stdin. EOF = Daemon weg: speichern und beenden.
async fn commands(core: Arc<Core>) {
    let mut lines = tokio::io::BufReader::new(tokio::io::stdin()).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        let line = line.trim().to_string();
        if line.is_empty() {
            continue;
        }
        let core = core.clone();
        tokio::task::spawn_blocking(move || {
            let reply = match serde_json::from_str::<Value>(&line) {
                Ok(cmd) => {
                    let id = cmd.get("id").cloned().unwrap_or(Value::Null);
                    match core.command(&cmd) {
                        Ok(result) => json!({"type": "reply", "id": id, "ok": true, "result": result}),
                        Err(error) => json!({"type": "reply", "id": id, "ok": false, "error": error}),
                    }
                }
                Err(e) => json!({"type": "reply", "id": null, "ok": false, "error": format!("kein JSON: {e}")}),
            };
            emit(&reply);
        });
    }
}

async fn shutdown_signal() {
    use tokio::signal::unix::{SignalKind, signal};
    let mut term = signal(SignalKind::terminate()).expect("SIGTERM");
    tokio::select! {
        _ = term.recv() => {}
        _ = tokio::signal::ctrl_c() => {}
    }
}

async fn run_live(args: Args) {
    let ping = Arc::new(PingTracker::with_perf_clock(platform::clock::perf_clock()));
    let core = Core::new(&args, ping.clone());
    let ports = Arc::new(CombatPortDetector::new());
    if let Some(dev) = &args.device {
        ports.set_preferred_device(Some(dev.clone()));
    }
    if let Some(dir) = &args.save_packets {
        let _ = std::fs::create_dir_all(dir);
        logging::logger::set_packet_log_enabled(true, dir);
        info!("Pakete werden nach {} geschrieben", dir.display());
    }

    let pcap = platform::pcap::library_available();
    let caps = platform::admin::is_admin();
    if !pcap {
        warn!("libpcap nicht gefunden, kein Mitschnitt");
    }
    if !caps {
        warn!("ohne cap_net_raw: sudo setcap cap_net_raw=ep {}", std::env::current_exe().unwrap_or_default().display());
    }
    emit(&json!({
        "type": "hello",
        "version": env!("CARGO_PKG_VERSION"),
        "parser": rederive::parser_version(),
        "pcap": pcap,
        "cap_net_raw": caps,
        "history_dir": args.history_dir,
    }));

    let (tx, rx) = mpsc::channel::<CapturedPayload>(4096);
    let capturer = PcapCapturer::new(tx);
    if pcap {
        capturer.start();
    }
    let mut dispatcher =
        CaptureDispatcher::new(core.storage.clone(), core.skills.clone(), core.npcs.clone(), ports.clone(), ping);
    dispatcher.set_dot_skill_ids(core.dot_ids.clone());
    dispatcher.use_suspend_flag(core.suspended.clone());
    tokio::spawn(async move { dispatcher.run(rx).await });
    let stdin_done = tokio::spawn(commands(core.clone()));

    {
        let core = core.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(args.interval);
            interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            let mut last = String::new();
            loop {
                interval.tick().await;
                let c = core.clone();
                last = tokio::task::spawn_blocking(move || {
                    tick(&c, &mut last);
                    last
                })
                .await
                .unwrap_or_default();
            }
        });
    }
    {
        let core = core.clone();
        let ports = ports.clone();
        tokio::spawn(async move {
            let mut last = Value::Null;
            loop {
                let s = status(&core, Some(&ports), pcap && caps);
                if s != last {
                    emit(&s);
                    last = s;
                }
                tokio::time::sleep(STATUS_EVERY).await;
            }
        });
    }
    {
        let core = core.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(HISTORY_EVERY).await;
                let c = core.clone();
                let _ = tokio::task::spawn_blocking(move || c.save(false)).await;
            }
        });
    }

    // Ende: Daemon schließt stdin oder schickt SIGTERM. Vorher alles speichern.
    tokio::select! {
        _ = shutdown_signal() => {}
        _ = stdin_done => info!("stdin geschlossen"),
    }
    finish(&core).await;
}

async fn finish(core: &Arc<Core>) {
    let c = core.clone();
    let _ = tokio::task::spawn_blocking(move || c.save(true)).await;
    emit(&json!({"type": "bye"}));
}

/// Einen Mitschnitt (`packets_*.txt`, wie `--save-packets` oder das Meter ihn schreibt) durch
/// denselben Parser schicken. Ohne Port-Erkennung und ohne Prüfung auf das laufende Spiel.
async fn run_replay(args: Args, file: &Path) {
    let packets = match share::read_capture(file) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };
    let core = Core::new(&args, Arc::new(PingTracker::new()));
    emit(&json!({"type": "hello", "version": env!("CARGO_PKG_VERSION"), "parser": rederive::parser_version(),
                 "replay": file, "packets": packets.len(), "history_dir": args.history_dir}));
    let mut proc = StreamProcessor::new(core.storage.clone(), core.skills.clone(), core.npcs.clone());
    proc.set_dot_skill_ids(core.dot_ids.clone());
    let mut streams: std::collections::HashMap<String, PacketAccumulator> = Default::default();
    let step = args.interval.as_millis() as i64;
    let first = packets.first().map(|p| p.captured_at_ms).unwrap_or(0);
    let (mut next_tick, mut next_save) = (first + step, first + HISTORY_EVERY.as_millis() as i64);
    let mut last = String::new();
    let mut prev = first;
    for p in &packets {
        if args.realtime && p.captured_at_ms > prev {
            tokio::time::sleep(Duration::from_millis((p.captured_at_ms - prev) as u64)).await;
        }
        prev = p.captured_at_ms;
        proc.set_override_timestamp(Some(p.captured_at_ms));
        let acc = streams.entry(p.stream.clone()).or_insert_with(PacketAccumulator::new);
        acc.append(&p.bytes);
        let used = proc.consume_stream(acc.snapshot());
        if used > 0 {
            acc.discard_bytes(used);
        }
        if p.captured_at_ms >= next_tick {
            tick(&core, &mut last);
            next_tick = p.captured_at_ms + step;
        }
        if p.captured_at_ms >= next_save {
            core.save(false);
            next_save = p.captured_at_ms + HISTORY_EVERY.as_millis() as i64;
        }
    }
    tick(&core, &mut last);
    proc.set_override_timestamp(None);
    finish(&core).await;
}

#[tokio::main]
async fn main() {
    use std::io::IsTerminal;
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_ansi(std::io::stderr().is_terminal())
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn,deckbar_capture=info")),
        )
        .init();
    let args = parse_args();
    if !args.data_dir.join("i18n").join("skills").exists() {
        eprintln!("Datenordner fehlt oder unvollständig: {} (--data)", args.data_dir.display());
        std::process::exit(1);
    }
    match args.replay.clone() {
        Some(file) => run_replay(args, &file).await,
        None => run_live(args).await,
    }
}
