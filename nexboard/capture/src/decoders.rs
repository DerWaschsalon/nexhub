//! Plugin-Decoder als Tabelle Opcode → Decoder (Daemon: `deckbar_daemon/plugins.py`).
//!
//! Der Plugin-Host des Meters (`a2tools/src-tauri/src/plugins`) hängt an Tauri-Fenstern. Hier läuft
//! nur sein Datenteil, die Logik ist von dort übernommen: Decoder lesen aus Spielpaketen Zahlen und
//! sonst nichts, ein `self`-Feld lässt nur Ereignisse des eigenen Charakters durch. Die Decoder selbst
//! prüft und führt der Kern aus (`plugins::decoder`), also auch dessen Sperrliste fremder Pakete.
//! Früher prüfte jedes Paket jeden Decoder; jetzt nur die für sein Opcode.

use std::collections::HashMap;

use a2tools_dps_meter_lib::plugins::decoder::{Decoder, DecoderSpec};
use serde_json::{Value, json};

use crate::out::{Message, Out};

#[derive(Default)]
pub struct DecoderTable {
    by_opcode: HashMap<[u8; 2], Vec<(String, Decoder)>>,
}

/// Die Decoder eines Plugins prüfen. Ein kaputter Decoder sperrt nur sein Plugin.
fn compile_plugin(entry: &Value) -> Result<(String, Vec<Decoder>), String> {
    let plugin = entry.get("plugin").and_then(Value::as_str).ok_or("plugin fehlt")?.to_string();
    let specs: Vec<DecoderSpec> = serde_json::from_value(entry.get("decoders").cloned().unwrap_or_else(|| json!([])))
        .map_err(|e| format!("{plugin}: {e}"))?;
    let decoders =
        specs.iter().map(Decoder::compile).collect::<Result<Vec<_>, _>>().map_err(|e| format!("{plugin}: {e}"))?;
    Ok((plugin, decoders))
}

impl DecoderTable {
    /// Aus `{"plugin":"id","decoders":[…]}` je Plugin; zurück auch die Fehler je Plugin.
    pub fn compile(plugins: &[Value]) -> (Self, Vec<String>) {
        let mut table = Self::default();
        let mut errors = Vec::new();
        for entry in plugins {
            match compile_plugin(entry) {
                Ok((plugin, decoders)) => {
                    for decoder in decoders {
                        table.by_opcode.entry(decoder.opcode).or_default().push((plugin.clone(), decoder));
                    }
                }
                Err(e) => errors.push(e),
            }
        }
        (table, errors)
    }

    pub fn is_empty(&self) -> bool {
        self.by_opcode.is_empty()
    }

    /// Ein Spielpaket durch die Decoder seines Opcodes; `me` = eigene Figur (nur bei `self`-Feldern gefragt).
    pub fn decode(&self, opcode: [u8; 2], body: &[u8], me: impl Fn() -> Option<i64>, out: &Out, at: i64) {
        let Some(decoders) = self.by_opcode.get(&opcode) else { return };
        for (plugin, decoder) in decoders {
            let Some(data) = decoder.decode(body) else { continue };
            if let Some(field) = &decoder.self_field {
                let mine = me();
                if mine.is_none() || mine != data.get(field).and_then(Value::as_i64) {
                    continue;
                }
            }
            out.send(&Message::PluginFrame {
                plugin,
                event: format!("decoded:{}", decoder.name),
                data: &data,
                immediate: decoder.immediate,
                at,
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fremde_pakete_lehnt_der_kern_ab() {
        let entry = json!({ "plugin": "x", "decoders": [
            { "name": "wer", "opcode": "44 36", "fields": [{ "name": "id", "type": "u32" }] }
        ]});
        assert!(compile_plugin(&entry).is_err());
    }

    #[test]
    fn decoder_liest_zahlen_aus_dem_inhalt() {
        let entry = json!({ "plugin": "x", "decoders": [
            { "name": "seele", "opcode": "0D 90", "fields": [{ "type": "skip:1" }, { "name": "anzahl", "type": "u16" }] }
        ]});
        let (plugin, decoders) = compile_plugin(&entry).unwrap();
        assert_eq!(plugin, "x");
        assert_eq!(decoders[0].decode(&[9, 7, 0]).unwrap()["anzahl"], 7);
    }

    #[test]
    fn kaputter_decoder_trifft_nur_sein_plugin() {
        let (table, errors) = DecoderTable::compile(&[
            json!({ "plugin": "gut", "decoders": [{ "name": "seele", "opcode": "0D 90", "fields": [] }] }),
            json!({ "plugin": "kaputt", "decoders": [{ "name": "Gross", "opcode": "0D 90", "fields": [] }] }),
        ]);
        assert_eq!(errors.len(), 1);
        assert!(errors[0].starts_with("kaputt:"));
        assert_eq!(table.by_opcode[&[0x0D, 0x90]].len(), 1);
    }
}
