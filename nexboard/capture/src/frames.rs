//! Der Abgriff auf jedes Spielpaket (`frame_tap` des Kerns), einmal für alle Abnehmer.
//!
//! Abnehmer: die Plugin-Decoder (decoders.rs) und abonnierte Opcodes für Module des Daemons
//! (`subscribe_frames`, das Radar ab Umbauschritt 7). Ohne beides ist der Abgriff aus und kostet nichts.

use std::collections::HashSet;
use std::fmt::Write;
use std::sync::{Arc, Weak};

use a2tools_dps_meter_lib::capture::{frame_tap, stream_processor};
use a2tools_dps_meter_lib::combat::data_storage::DataStorage;
use parking_lot::RwLock;
use serde_json::{Value, json};

use crate::decoders::DecoderTable;
use crate::out::{Message, Out};

struct Taps {
    decoders: RwLock<DecoderTable>,
    raw: RwLock<HashSet<[u8; 2]>>, // Opcodes als Bytes im Paket (Little Endian)
    storage: Weak<DataStorage>,
    out: Out,
}

pub struct FrameTap {
    taps: Arc<Taps>,
}

fn now_ms() -> i64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_millis() as i64).unwrap_or_default()
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().fold(String::with_capacity(bytes.len() * 2), |mut text, b| {
        let _ = write!(text, "{b:02x}");
        text
    })
}

impl FrameTap {
    pub fn new(storage: &Arc<DataStorage>, out: Out) -> Self {
        let taps = Taps { decoders: RwLock::default(), raw: RwLock::default(), storage: Arc::downgrade(storage), out };
        Self { taps: Arc::new(taps) }
    }

    /// Ersetzt alle Plugin-Decoder. Antwort: Fehler je Plugin (der Daemon zeigt sie in den Einstellungen).
    pub fn set_decoders(&self, plugins: &[Value]) -> Value {
        let (table, errors) = DecoderTable::compile(plugins);
        *self.taps.decoders.write() = table;
        self.refresh();
        json!({ "errors": errors })
    }

    /// Ersetzt die abonnierten Opcodes; jedes Paket davon geht roh als `frame` an den Daemon.
    pub fn subscribe(&self, opcodes: &[u16]) {
        *self.taps.raw.write() = opcodes.iter().map(|op| op.to_le_bytes()).collect();
        self.refresh();
    }

    fn refresh(&self) {
        if self.taps.decoders.read().is_empty() && self.taps.raw.read().is_empty() {
            frame_tap::set(None);
            return;
        }
        let taps = self.taps.clone();
        frame_tap::set(Some(Arc::new(move |packet: &[u8]| on_frame(&taps, packet))));
    }
}

/// Ein Spielpaket: seine Länge als Varint, 2 Byte Typ, der Inhalt.
fn on_frame(taps: &Taps, packet: &[u8]) {
    let len = stream_processor::read_varint(packet, 0).length;
    if len <= 0 {
        return;
    }
    let at = len as usize;
    let Some(&[lo, hi]) = packet.get(at..at + 2) else { return };
    let (opcode, body) = ([lo, hi], &packet[at + 2..]);
    let now = now_ms();
    if taps.raw.read().contains(&opcode) {
        let op = u16::from_le_bytes(opcode);
        taps.out.send(&Message::Frame { op, data: hex(body), at: now });
    }
    let me = || taps.storage.upgrade().and_then(|s| s.local_player_id());
    taps.decoders.read().decode(opcode, body, me, &taps.out, now);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_ist_kleingeschrieben_und_lueckenlos() {
        assert_eq!(hex(&[0x0d, 0x90, 0xff]), "0d90ff");
    }
}
