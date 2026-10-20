//! Meter-Zeilen für Leiste und Overlay: Spieler am Ziel nach DPS, mit Klasse, Anteil und „du“.
//!
//! Übernommen aus dem A2Tools DPS Meter (GPL-3.0), `src-tauri/src/stream_overlay/snapshot.rs`
//! (`build`, `class_key`), weil das Modul dort am Online-Feature hängt. Geändert: eigener
//! Optionen-Typ ohne Settings-Anbindung, Icons und Tests nicht übernommen.

use a2tools_dps_meter_lib::entity::dps_data::DpsData;
use a2tools_dps_meter_lib::entity::job_class::JobClass;
use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct View {
    pub target: String,
    pub mode: String,
    #[serde(rename = "timeMs")]
    pub time_ms: i64,
    /// Rest-HP des Ziels in Prozent
    pub hp: Option<f64>,
    #[serde(rename = "targetId")]
    pub target_id: i32,
    pub boss: bool,
    pub rows: Vec<Row>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Row {
    pub id: i32,
    pub name: String,
    pub cls: Option<&'static str>,
    pub dps: i64,
    pub dmg: i64,
    pub pct: f64,
    pub you: bool,
    /// In der eigenen Gruppe: steht im Gruppen-Roster des Spiels (nur dort gibt es Kampfkraft
    /// bzw. Ausrüstungsstufe). Ohne Gruppe ist niemand markiert, auch „du“ nicht.
    pub party: bool,
}

#[derive(Debug, Clone)]
pub struct Options {
    pub limit: usize,
    pub pin_you: bool,
}

impl Default for Options {
    fn default() -> Self {
        Self { limit: 8, pin_you: false }
    }
}

const ALL_CLASSES: [JobClass; 9] = [
    JobClass::Gladiator,
    JobClass::Templar,
    JobClass::Ranger,
    JobClass::Assassin,
    JobClass::Sorcerer,
    JobClass::Cleric,
    JobClass::Elementalist,
    JobClass::Chanter,
    JobClass::Fighter,
];

/// Englischer Schlüssel wie im Stream-Overlay (passt zu `dps.CLASSES` im Daemon).
pub fn class_key(class: JobClass) -> &'static str {
    match class {
        JobClass::Gladiator => "gladiator",
        JobClass::Templar => "templar",
        JobClass::Ranger => "ranger",
        JobClass::Assassin => "assassin",
        JobClass::Sorcerer => "sorcerer",
        JobClass::Cleric => "cleric",
        JobClass::Elementalist => "spiritmaster",
        JobClass::Chanter => "chanter",
        JobClass::Fighter => "brawler",
    }
}

fn class_of_job(job: &str) -> Option<JobClass> {
    let job = job.trim();
    ALL_CLASSES.into_iter().find(|c| c.class_name() == job)
}

struct Candidate {
    id: i32,
    name: String,
    identified: bool,
    class: Option<JobClass>,
    dps: i64,
    dmg: i64,
    party: bool,
}

pub fn build(dps: &DpsData, opts: &Options) -> View {
    // Ein Name, eine Zeile: wechselt ein Spieler die Entity-ID (Zonenwechsel), stehen beide im
    // Map. Es bleibt die mit Klasse und Namen, sonst die neuere ID.
    let mut by_name: Vec<Candidate> = Vec::new();
    for (&id, row) in &dps.map {
        if id <= 0 || !row.dps.is_finite() {
            continue;
        }
        let id_text = id.to_string();
        let identified = !row.nickname.is_empty() && row.nickname != id_text;
        let name = if identified { row.nickname.clone() } else { format!("#{id}") };
        let next = Candidate {
            id,
            name,
            identified,
            class: class_of_job(&row.job),
            dps: row.dps.trunc() as i64,
            dmg: row.amount.trunc() as i64,
            party: row.combat_power > 0 || row.gear_score > 0,
        };
        let score = |c: &Candidate| (c.class.is_some() as u8) * 2 + c.identified as u8;
        match by_name.iter_mut().find(|c| c.name == next.name) {
            None => by_name.push(next),
            Some(existing) => {
                let (old, new) = (score(existing), score(&next));
                if new > old || (new == old && next.id > existing.id) {
                    *existing = next;
                }
            }
        }
    }
    by_name.sort_by(|a, b| b.dps.cmp(&a.dps).then(a.id.cmp(&b.id)));

    let local = dps.local_player_id.and_then(|id| i32::try_from(id).ok());
    let is_you = |c: &Candidate| local.is_some_and(|id| id == c.id);

    // Trainingspuppe: nur die eigene Zeile
    if dps.target_mode == "trainTargets" && by_name.iter().any(is_you) {
        by_name.retain(is_you);
    }

    // Top N, die eigene Zeile und die eigene Gruppe immer dabei (notfalls dahinter)
    let limit = opts.limit.max(1);
    let mut shown: Vec<&Candidate> = by_name.iter().take(limit).collect();
    for c in by_name.iter().skip(limit) {
        if is_you(c) || c.party {
            shown.push(c);
        }
    }
    if opts.pin_you {
        if let Some(pos) = shown.iter().position(|c| is_you(c)) {
            let you = shown.remove(pos);
            shown.insert(0, you);
        }
    }

    let total: i64 = shown.iter().map(|c| c.dmg.max(0)).sum();
    let rows = shown
        .into_iter()
        .map(|c| Row {
            id: c.id,
            name: c.name.clone(),
            cls: c.class.map(class_key),
            dps: c.dps,
            dmg: c.dmg,
            pct: if total > 0 { round1(c.dmg.max(0) as f64 * 100.0 / total as f64) } else { 0.0 },
            you: is_you(c),
            party: c.party,
        })
        .collect();

    let hp = (dps.target_max_hp > 0).then(|| {
        let left = if dps.target_current_hp >= 0 {
            dps.target_current_hp
        } else {
            dps.target_max_hp - dps.target_total_damage
        };
        round1((left as f64 * 100.0 / dps.target_max_hp as f64).clamp(0.0, 100.0))
    });

    View {
        target: dps.target_name.trim().to_string(),
        mode: dps.target_mode.clone(),
        time_ms: dps.battle_time.max(0),
        hp,
        target_id: dps.target_id,
        boss: dps.target_is_boss,
        rows,
    }
}

fn round1(x: f64) -> f64 {
    (x * 10.0).round() / 10.0
}

#[cfg(test)]
mod tests {
    use super::*;
    use a2tools_dps_meter_lib::entity::personal_data::PersonalData;

    fn row(nick: &str, job: &str, dps: f64, amount: f64) -> PersonalData {
        let mut p = PersonalData::with_job(nick.to_string(), job.to_string());
        p.dps = dps;
        p.amount = amount;
        p
    }

    fn sample() -> DpsData {
        let mut d = DpsData::new();
        d.target_name = " Boss ".into();
        d.battle_time = 65_000;
        d.target_max_hp = 1000;
        d.target_total_damage = 250;
        d.local_player_id = Some(3);
        d.map.insert(1, row("Alpha", "검성", 3000.0, 300_000.0));
        d.map.insert(2, row("Bravo", "치유성", 1000.0, 100_000.0));
        d.map.insert(3, row("Me", "Unknown", 2000.0, 200_000.0));
        d.map.insert(-5, row("Ghost", "검성", 9999.0, 1.0));
        d.map.insert(7, row("7", "", 10.0, 1000.0));
        d
    }

    #[test]
    fn rows_sorted_with_class_share_and_you() {
        let v = build(&sample(), &Options::default());
        assert_eq!(v.target, "Boss");
        assert_eq!(v.hp, Some(75.0));
        let names: Vec<_> = v.rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["Alpha", "Me", "Bravo", "#7"]);
        assert_eq!(v.rows[0].cls, Some("gladiator"));
        assert_eq!(v.rows[2].cls, Some("cleric"));
        assert!(v.rows[1].you && !v.rows[0].you);
        assert_eq!(v.rows[0].pct, 49.9);
    }

    #[test]
    fn you_stay_visible_beyond_limit_and_pin() {
        let v = build(&sample(), &Options { limit: 1, pin_you: false });
        let names: Vec<_> = v.rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["Alpha", "Me"]);
        let v = build(&sample(), &Options { limit: 2, pin_you: true });
        assert_eq!(v.rows[0].name, "Me");
    }

    #[test]
    fn party_members_are_marked_and_never_cut() {
        let mut d = sample();
        d.map.get_mut(&2).unwrap().combat_power = 41_000;
        d.map.get_mut(&3).unwrap().gear_score = 3100;
        let v = build(&d, &Options { limit: 1, pin_you: false });
        let rows: Vec<_> = v.rows.iter().map(|r| (r.name.as_str(), r.party)).collect();
        assert_eq!(rows, [("Alpha", false), ("Me", true), ("Bravo", true)]);
    }
}
