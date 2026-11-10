//! Effekte, die gerade laufen: auf dem aktuellen Ziel und auf dir (`active_effects`).
//!
//! Für andere Programme auf diesem PC (Daemon: boss_effekte.py, GET /api/radar/kampf). Vorher fragte
//! der Daemon bis zu fünfmal je Sekunde den Kontext und alle Buff-Spuren des Kampfes ab und suchte die
//! laufenden selbst heraus; jetzt geht nur das Ergebnis über die Leitung.

use a2tools_dps_meter_lib::combat::fight_buffs::{BuffTrack, LiveFightBuffs, end_code};
use serde_json::{Value, json};

use crate::core::Core;

/// Der Kern rechnet bis zum letzten Treffer. Trifft so lange niemand mehr, gilt der Stand als veraltet
/// (Lakshmis Schadensreflexion dauert 8 s, in der Zeit greifen manche nicht an).
const MAX_IDLE_MS: i64 = 10_000;

fn now_ms() -> i64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_millis() as i64).unwrap_or_default()
}

/// `{"boss_effekte": [{"id", "seit"}], "eigene_effekte": […] | null}`; null = eigene Figur unbekannt.
pub fn active(core: &Core) -> Value {
    let empty = json!({ "boss_effekte": [], "eigene_effekte": null });
    let target = core.storage.current_target();
    if target == 0 {
        return empty;
    }
    let Some(fight) = core.reader().live_fight_buffs(target, &[]) else { return empty };
    running_effects(&fight, core.storage.local_player_id(), now_ms()).unwrap_or(empty)
}

fn running_effects(fight: &LiveFightBuffs, me: Option<i64>, now: i64) -> Option<Value> {
    if now - fight.start_time_ms - fight.duration_ms > MAX_IDLE_MS {
        return None;
    }
    let own = me.and_then(|id| i32::try_from(id).ok()).map(|id| running_on(fight, id, now));
    Some(json!({ "boss_effekte": running_on(fight, fight.target_id, now), "eigene_effekte": own }))
}

/// Effekte auf `on`, deren letzter Abschnitt noch läuft, mit Sekunden seit seinem Beginn.
fn running_on(fight: &LiveFightBuffs, on: i32, now: i64) -> Vec<Value> {
    fight
        .buffs
        .iter()
        .filter(|track| track.on == on)
        .filter_map(|track| still_on_since(track, fight.start_time_ms, now))
        .collect()
}

fn still_on_since(track: &BuffTrack, fight_start: i64, now: i64) -> Option<Value> {
    let last = *track.segments().last()?;
    if last.how != end_code::STILL_ON {
        return None;
    }
    let seconds = (now - fight_start - last.start) as f64 / 1000.0;
    Some(json!({ "id": track.id, "seit": (seconds * 10.0).round() / 10.0 }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn track(on: i32, id: u32, segs: &str) -> BuffTrack {
        BuffTrack { on, summon: false, id, by: 0, skill: 0, passive: false, segs: segs.into(), up: 0 }
    }

    fn fight(buffs: Vec<BuffTrack>) -> LiveFightBuffs {
        LiveFightBuffs { target_id: 77, start_time_ms: 1_000_000, duration_ms: 30_000, buffs, stagger: vec![] }
    }

    #[test]
    fn nur_laufende_auf_ziel_und_mir() {
        let f = fight(vec![
            track(77, 1, "0,5000,1,1;20000,30000,1,10"), // läuft seit 20 s ab Kampfbeginn
            track(77, 2, "0,5000,1,1"),                  // abgelaufen
            track(5, 3, "25000,30000,1,10"),             // auf mir
            track(9, 4, "25000,30000,1,10"),             // auf jemand anderem
        ]);
        let now = 1_000_000 + 31_500;
        let v = running_effects(&f, Some(5), now).unwrap();
        assert_eq!(v["boss_effekte"], json!([{ "id": 1, "seit": 11.5 }]));
        assert_eq!(v["eigene_effekte"], json!([{ "id": 3, "seit": 6.5 }]));
        assert_eq!(running_effects(&f, None, now).unwrap()["eigene_effekte"], Value::Null);
    }

    #[test]
    fn alter_stand_zaehlt_nicht() {
        let f = fight(vec![track(77, 1, "20000,30000,1,10")]);
        assert!(running_effects(&f, None, 1_000_000 + 30_000 + MAX_IDLE_MS + 1).is_none());
    }
}
