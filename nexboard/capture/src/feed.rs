//! Spieldaten für die A2Tools-Plugins, die nicht aus einzelnen Paketen kommen (Daemon:
//! `deckbar_daemon/plugins.py`): der eigene Charakter und die Meldungen, die im Meter dessen
//! Ereignis-Schleife liest (Feldboss-Karte, Abyss, Todesursachen, Würfeln).
//!
//!   stdout  {"type":"plugin_character","data":…}         bei jeder Änderung
//!           {"type":"plugin_feed","event":"bossMap"|"abyss"|"deathRecap"|"lootRoll","data":…,"at":ms}

use std::sync::Arc;

use a2tools_dps_meter_lib::capture::abyss_artifacts::ArtifactState;
use a2tools_dps_meter_lib::capture::boss_map::BossMap;
use a2tools_dps_meter_lib::combat::data_storage::DataStorage;
use serde_json::{Value, json};

use crate::out::{Message, Out};

/// Wer spielt, wie ihn Plugins mit `events:character` sehen (wie `character` im Plugin-Host).
fn character(storage: &DataStorage) -> Value {
    let p = storage.local_profile();
    let list = storage.entry_list();
    let theirs = matches!((list.owner.as_deref(), p.name.as_deref()), (Some(o), Some(n)) if o.trim() == n.trim());
    let odyle =
        list.odyle_energy.filter(|_| theirs).map(|(basic, charged)| json!({ "basic": basic, "charged": charged }));
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
    fn poll(&mut self, storage: &DataStorage, out: &Out) {
        let now = character(storage);
        if self.told.as_ref() != Some(&now) {
            out.send(&Message::PluginCharacter { data: &now });
            self.told = Some(now);
        }
        let feed = |event: &str, at: i64, data: Value| out.send(&Message::PluginFeed { event, at, data: &data });
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

/// So oft wie im Meter dessen Ereignis-Schleife liest
const POLL_EVERY: std::time::Duration = std::time::Duration::from_millis(250);

/// Alle POLL_EVERY: dieselben Daten, die im Meter dessen Ereignis-Schleife liest.
pub async fn watch(storage: Arc<DataStorage>, out: Out) {
    let mut feed = Feed::default();
    let mut interval = tokio::time::interval(POLL_EVERY);
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        interval.tick().await;
        feed.poll(&storage, &out);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn charakter_ist_ohne_daten_leer_aber_vollstaendig() {
        let storage = DataStorage::new();
        let c = character(&storage);
        assert!(c["name"].is_null() && c["odyleEnergy"].is_null());
        assert!(c.get("contentTimes").is_some());
    }
}
