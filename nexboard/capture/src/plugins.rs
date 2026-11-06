//! Spieldaten für die A2Tools-Plugins (Daemon: `deckbar_daemon/plugins.py`).
//!
//! Der Plugin-Host des Meters (`a2tools/src-tauri/src/plugins`) hängt an Tauri-Fenstern. Hier läuft
//! nur sein Datenteil, die Logik ist von dort übernommen: Decoder lesen aus Spielpaketen Zahlen und
//! sonst nichts, ein `self`-Feld lässt nur Ereignisse des eigenen Charakters durch. Die Decoder selbst
//! prüft und führt der Kern aus (`plugins::decoder`), also auch dessen Sperrliste fremder Pakete.
//!
//!   stdin   {"cmd":"plugin_decoders","plugins":[{"plugin":"id","decoders":[…]}]}
//!   stdout  {"type":"plugin_frame","plugin":"id","event":"decoded:name","data":…,"immediate":bool,"at":ms}
//!           {"type":"plugin_character","data":…}         bei jeder Änderung
//!           {"type":"plugin_feed","event":"bossMap"|"abyss"|"deathRecap"|"lootRoll","data":…,"at":ms}

use std::sync::{Arc, Weak};

use a2tools_dps_meter_lib::capture::abyss_artifacts::ArtifactState;
use a2tools_dps_meter_lib::capture::boss_map::BossMap;
use a2tools_dps_meter_lib::capture::{frame_tap, stream_processor};
use a2tools_dps_meter_lib::combat::data_storage::DataStorage;
use a2tools_dps_meter_lib::plugins::decoder::{Decoder, DecoderSpec};
use serde_json::{json, Value};

fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or_default()
}

/// Die Decoder eines Plugins prüfen. Ein kaputter Decoder sperrt nur sein Plugin.
fn compile(entry: &Value) -> Result<(String, Vec<Decoder>), String> {
    let plugin = entry.get("plugin").and_then(Value::as_str).ok_or("plugin fehlt")?.to_string();
    let specs: Vec<DecoderSpec> =
        serde_json::from_value(entry.get("decoders").cloned().unwrap_or_else(|| json!([]))).map_err(|e| format!("{plugin}: {e}"))?;
    let decoders = specs.iter().map(Decoder::compile).collect::<Result<Vec<_>, _>>().map_err(|e| format!("{plugin}: {e}"))?;
    Ok((plugin, decoders))
}

/// Ersetzt alle Decoder. Antwort: Fehler je Plugin (der Daemon zeigt sie in den Einstellungen).
pub fn set_decoders(storage: &Arc<DataStorage>, plugins: &[Value]) -> Value {
    let mut loaded = Vec::new();
    let mut errors = Vec::new();
    for entry in plugins {
        match compile(entry) {
            Ok((plugin, decoders)) if !decoders.is_empty() => loaded.push((plugin, decoders)),
            Ok(_) => {}
            Err(e) => errors.push(e),
        }
    }
    if loaded.is_empty() {
        frame_tap::set(None);
    } else {
        let storage: Weak<DataStorage> = Arc::downgrade(storage);
        frame_tap::set(Some(Arc::new(move |packet: &[u8]| on_frame(&loaded, &storage, packet))));
    }
    json!({ "errors": errors })
}

/// Ein Spielpaket: seine Länge als Varint, 2 Byte Typ, der Inhalt.
fn on_frame(plugins: &[(String, Vec<Decoder>)], storage: &Weak<DataStorage>, packet: &[u8]) {
    let len = stream_processor::read_varint(packet, 0).length;
    if len <= 0 {
        return;
    }
    let at = len as usize;
    let Some(opcode) = packet.get(at..at + 2) else { return };
    let body = &packet[at + 2..];
    for (plugin, decoders) in plugins {
        for d in decoders.iter().filter(|d| d.opcode == opcode) {
            let Some(data) = d.decode(body) else { continue };
            if let Some(field) = &d.self_field {
                let me = storage.upgrade().and_then(|s| s.local_player_id());
                if me.is_none() || me != data.get(field).and_then(Value::as_i64) {
                    continue;
                }
            }
            crate::emit(&json!({
                "type": "plugin_frame",
                "plugin": plugin,
                "event": format!("decoded:{}", d.name),
                "data": data,
                "immediate": d.immediate,
                "at": now_ms(),
            }));
        }
    }
}

/// Wer spielt, wie ihn Plugins mit `events:character` sehen (wie `character` im Plugin-Host).
fn character(storage: &DataStorage) -> Value {
    let p = storage.local_profile();
    let list = storage.entry_list();
    let theirs = matches!((list.owner.as_deref(), p.name.as_deref()), (Some(o), Some(n)) if o.trim() == n.trim());
    let odyle = list.odyle_energy.filter(|_| theirs).map(|(basic, charged)| json!({ "basic": basic, "charged": charged }));
    let content = (theirs && !list.counts.is_empty()).then(|| json!(list.counts));
    let shop = (theirs && !list.shop_limits.is_empty()).then(|| json!(list.shop_limits));
    let crafts = (theirs && !list.crafts.is_empty()).then(|| json!(list.crafts));
    json!({
        "name": p.name,
        "serverId": p.server_id,
        "level": p.level,
        "class": p.class.map(|c| c.class_name().to_string()),
        "combatPower": p.combat_power,
        "gearScore": p.gear_score,
        "odyleEnergy": odyle,
        "contentCounts": content,
        "shopLimits": shop,
        "crafts": crafts,
        "kinahToday": list.kinah_today.filter(|_| theirs),
        "abyssPoints": list.abyss_points.filter(|_| theirs).map(|(p, l)| [p, l]),
        "contentTimes": Some(list.times).filter(|t| theirs && !t.is_empty()),
    })
}

fn abyss_event(state: &ArtifactState, seen_ms: i64) -> Value {
    let secs = |ms: i64| (ms > 0).then_some(ms / 1000);
    let wars: Vec<_> = state
        .wars
        .iter()
        .map(|w| json!({ "event": w.event_id, "since": secs(w.since_ms), "until": secs(w.until_ms) }))
        .collect();
    let artifacts: Vec<_> =
        state.artifacts.iter().map(|a| json!({ "id": a.id, "event": a.event_id(), "owner": a.owner.name() })).collect();
    json!({ "observedAt": seen_ms / 1000, "wars": wars, "artifacts": artifacts })
}

fn boss_map_event(map: &BossMap) -> Value {
    let secs = |ms: i64| (ms > 0).then_some(ms / 1000);
    let bosses: serde_json::Map<String, Value> = map
        .bosses
        .iter()
        .map(|b| {
            let entry = json!({
                "state": if b.up { "up" } else { "dead" },
                "upSince": if b.up { secs(b.time_ms) } else { None },
                "nextSpawn": if b.up { None } else { secs(b.time_ms) },
                "reportedAt": map.seen_ms / 1000,
                "confirmed": true,
            });
            (b.id.to_string(), entry)
        })
        .collect();
    json!({ "map": map.map_id, "bosses": bosses })
}

/// Liest, was sich seit dem letzten Aufruf getan hat, und meldet es (Takt: `watch`).
#[derive(Default)]
struct Feed {
    told: Option<Value>,
    map_seq: u64,
    abyss_seq: u64,
    recap_seq: u64,
    roll_seq: u64,
}

impl Feed {
    fn poll(&mut self, storage: &DataStorage) {
        let now = character(storage);
        if self.told.as_ref() != Some(&now) {
            crate::emit(&json!({ "type": "plugin_character", "data": now }));
            self.told = Some(now);
        }
        let feed = |event: &str, at: i64, data: Value| {
            crate::emit(&json!({ "type": "plugin_feed", "event": event, "at": at, "data": data }));
        };
        if let Some((next, maps)) = storage.boss_maps_since(self.map_seq) {
            self.map_seq = next;
            if let Some(map) = maps.iter().filter(|m| m.header == 0).max_by_key(|m| m.seen_ms) {
                feed("bossMap", map.seen_ms, boss_map_event(map));
            }
        }
        if let Some((next, artifacts, seen_ms)) = storage.abyss_artifacts_since(self.abyss_seq) {
            self.abyss_seq = next;
            if !artifacts.artifacts.is_empty() {
                feed("abyss", seen_ms, abyss_event(&artifacts, seen_ms));
            }
        }
        if let Some((next, recaps)) = storage.death_recaps_since(self.recap_seq) {
            self.recap_seq = next;
            for recap in recaps {
                feed("deathRecap", recap.at, serde_json::to_value(&recap).unwrap_or_default());
            }
        }
        if let Some((next, rolls)) = storage.loot_rolls_since(self.roll_seq) {
            self.roll_seq = next;
            for roll in rolls {
                feed("lootRoll", roll.at, serde_json::to_value(&roll).unwrap_or_default());
            }
        }
    }
}

/// Alle 250 ms: dieselben Daten, die im Meter dessen Ereignis-Schleife liest.
pub async fn watch(storage: Arc<DataStorage>) {
    let mut feed = Feed::default();
    let mut interval = tokio::time::interval(std::time::Duration::from_millis(250));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        interval.tick().await;
        feed.poll(&storage);
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
        assert!(compile(&entry).is_err());
    }

    #[test]
    fn decoder_liest_zahlen_aus_dem_inhalt() {
        let entry = json!({ "plugin": "x", "decoders": [
            { "name": "seele", "opcode": "0D 90", "fields": [{ "type": "skip:1" }, { "name": "anzahl", "type": "u16" }] }
        ]});
        let (plugin, decoders) = compile(&entry).unwrap();
        assert_eq!(plugin, "x");
        assert_eq!(decoders[0].decode(&[9, 7, 0]).unwrap()["anzahl"], 7);
    }

    #[test]
    fn kaputter_decoder_trifft_nur_sein_plugin() {
        let storage = Arc::new(DataStorage::new());
        let out = set_decoders(&storage, &[
            json!({ "plugin": "gut", "decoders": [] }),
            json!({ "plugin": "kaputt", "decoders": [{ "name": "Gross", "opcode": "0D 90", "fields": [] }] }),
        ]);
        let errors = out["errors"].as_array().unwrap();
        assert_eq!(errors.len(), 1);
        assert!(errors[0].as_str().unwrap().starts_with("kaputt:"));
        frame_tap::set(None);
    }

    #[test]
    fn charakter_ist_ohne_daten_leer_aber_vollstaendig() {
        let storage = DataStorage::new();
        let c = character(&storage);
        assert!(c["name"].is_null() && c["odyleEnergy"].is_null());
        assert!(c.get("contentTimes").is_some());
    }
}
