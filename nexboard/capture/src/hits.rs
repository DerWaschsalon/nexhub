//! Einzeltreffer für den Hub (NexLog, siehe proto/README.md).
//!
//! Der A2Tools-Kern zählt Treffer nur zusammen: Schaden pro Fähigkeit, dazu die Zeitpunkte der
//! Treffer. Über den Haken `DataStorage::set_on_hit` (patches/a2tools-on-hit.patch) kommt jeder
//! Treffer mit eigenem Schaden und eigenen Merkmalen hier an. Beim Speichern eines Kampfes landen
//! seine Treffer in `<history-dir>/hits/<kampf-id>.json`, neben `history/<kampf-id>.json`.
//!
//! Dateiformat (eine Zeile pro Treffer, Zeit relativ zum Kampfbeginn):
//!
//!   {"version":1,"fight":"auto_…","target":37797,"start_ms":…,
//!    "columns":["t_ms","actor","owner","skill","damage","multi","flags"],
//!    "flags":{"crit":1,"back":2,…},"rows":[[1520,8731,0,17030000,31332,0,3],…]}
//!
//! `owner` ist bei Beschwörungen die Figur dahinter, sonst 0. `skill` ist der Code, unter dem das
//! Meter die Fähigkeit führt (Varianten unter dem Grundcode), passend zu `details.skills[].code` der
//! Kampfdatei. `damage` enthält Mehrfachtreffer (`multi` = deren Anzahl), wie die Summen des Meters.

use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};

use a2tools_dps_meter_lib::entity::damage_packet::ParsedDamagePacket;
use a2tools_dps_meter_lib::entity::fight_record::FightRecord;
use a2tools_dps_meter_lib::entity::special_damage::SpecialDamage;
use a2tools_dps_meter_lib::entity::summon_resolver;
use a2tools_dps_meter_lib::i18n::lookup::SkillLookup;
use parking_lot::Mutex;
use serde_json::json;

/// Höchstens so viele Treffer im Speicher (je 32 Bytes, also gut 10 MB). Ein Bosskampf hat
/// meist 2 000–6 000 Treffer; was älter als `KEEP_MS` ist, fliegt ohnehin raus.
const MAX_HITS: usize = 300_000;
const KEEP_MS: i64 = 2 * 60 * 60 * 1000;
/// Treffer, die so kurz nach dem gespeicherten Kampfende landen, gehören noch dazu
const END_GRACE_MS: i64 = 1000;

/// Merkmale eines Treffers als Bits; die Namen stehen in jeder Datei mit.
const FLAGS: [(&str, u16); 11] = [
    ("crit", 1),
    ("back", 2),
    ("frontal", 4),
    ("perfect", 8),
    ("double", 16),
    ("parry", 32),
    ("shield_block", 64),
    ("iron_wall", 128),
    ("regeneration", 256),
    ("perfect_block", 512),
    ("dot", 1024),
];

fn flag(name: &str) -> u16 {
    FLAGS.iter().find(|(n, _)| *n == name).map(|(_, b)| *b).unwrap_or(0)
}

#[derive(Clone, Copy)]
struct Hit {
    t: i64,
    actor: i32,
    target: i32,
    skill: i32,
    damage: i32,
    multi: i32,
    flags: u16,
}

impl Hit {
    fn from_packet(p: &ParsedDamagePacket) -> Self {
        let mut flags = if p.is_dot() { flag("dot") } else { 0 };
        for s in p.specials() {
            flags |= flag(match s {
                SpecialDamage::Critical => "crit",
                SpecialDamage::Back => "back",
                SpecialDamage::Frontal => "frontal",
                SpecialDamage::Perfect => "perfect",
                SpecialDamage::Double => "double",
                SpecialDamage::Parry => "parry",
                SpecialDamage::ShieldBlock => "shield_block",
                SpecialDamage::IronWall => "iron_wall",
                SpecialDamage::Regeneration => "regeneration",
                SpecialDamage::PerfectBlock => "perfect_block",
            });
        }
        Self {
            t: p.timestamp(),
            actor: p.actor_id(),
            target: p.target_id(),
            skill: p.skill_code(),
            damage: p.total_damage(),
            multi: p.multi_hit_count(),
            flags,
        }
    }
}

/// Code, unter dem das Meter eine Fähigkeit zeigt: eine Variante (letzte vier Stellen ≠ 0) zählt
/// zum Grundcode, wenn sie keinen eigenen Namen hat. Gleiche Regel wie in
/// `DpsCalculator::get_target_details` des Kerns (dort ohne eigene Funktion).
fn meter_skill_code(raw: i32, skills: &SkillLookup) -> i32 {
    let base = raw - raw % 10_000;
    let base_name = skills.get_skill_name(base);
    if base_name.is_empty() {
        return raw;
    }
    let raw_name = skills.get_skill_name(raw);
    if raw_name.is_empty() || raw_name == base_name { base } else { raw }
}

/// Die letzten Treffer, nach Zeit geordnet (so wie sie ankommen).
pub struct HitLog {
    hits: Mutex<VecDeque<Hit>>,
    dir: PathBuf,
}

impl HitLog {
    pub fn new(history_dir: &Path) -> Self {
        Self { hits: Mutex::new(VecDeque::new()), dir: history_dir.join("hits") }
    }

    /// Aus dem Haken des Kerns: nur kopieren, der Kern hält dabei seine Sperre.
    pub fn record(&self, packet: &ParsedDamagePacket) {
        let hit = Hit::from_packet(packet);
        let mut hits = self.hits.lock();
        hits.push_back(hit);
        while hits.len() > MAX_HITS || hits.front().is_some_and(|h| hit.t - h.t > KEEP_MS) {
            hits.pop_front();
        }
    }

    /// Treffer eines gespeicherten Kampfes nach `hits/<id>.json` schreiben.
    /// `summons` ordnet Beschwörungen ihrer Figur zu (`DataStorage::get_summon_data`).
    pub fn save_fight(&self, record: &FightRecord, summons: &HashMap<i32, i32>, skills: &SkillLookup)
        -> std::io::Result<usize> {
        let start = record.start_time_ms;
        let end = start + record.duration_ms + END_GRACE_MS;
        let rows: Vec<[i64; 7]> = self
            .hits
            .lock()
            .iter()
            .filter(|h| h.target == record.target_id && h.t >= start && h.t <= end)
            .map(|h| {
                let owner = summon_resolver::resolve(h.actor, summons);
                let owner = if owner == h.actor { 0 } else { owner };
                let skill = meter_skill_code(h.skill, skills);
                [h.t - start, h.actor.into(), owner.into(), skill.into(), h.damage.into(), h.multi.into(), h.flags.into()]
            })
            .collect();
        let doc = json!({
            "version": 1,
            "fight": record.id,
            "target": record.target_id,
            "start_ms": start,
            "columns": ["t_ms", "actor", "owner", "skill", "damage", "multi", "flags"],
            "flags": FLAGS.iter().map(|(n, b)| (n.to_string(), json!(b))).collect::<serde_json::Map<_, _>>(),
            "rows": rows,
        });
        std::fs::create_dir_all(&self.dir)?;
        // Erst vollständig schreiben, dann umbenennen: der Daemon liest nie eine halbe Datei
        let path = self.dir.join(format!("{}.json", record.id));
        let tmp = path.with_extension("json.tmp");
        std::fs::write(&tmp, doc.to_string())?;
        std::fs::rename(&tmp, &path)?;
        Ok(rows.len())
    }

    /// Zum gelöschten Kampf gehörende Treffer mit löschen.
    pub fn delete_fight(&self, id: &str) {
        let _ = std::fs::remove_file(self.dir.join(format!("{id}.json")));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use a2tools_dps_meter_lib::combat::data_storage::DataStorage;
    use std::sync::Arc;

    fn packet(t: i64, damage: i32) -> ParsedDamagePacket {
        let mut p = ParsedDamagePacket::new();
        p.set_actor_id(8731);
        p.set_target_id(37797);
        p.set_skill_code(17_030_000); // Klassen-Fähigkeit (Bogen), damit der Kern den Treffer zählt
        p.set_damage(damage);
        p.set_timestamp(t);
        p
    }

    #[test]
    fn treffer_mit_merkmalen_und_mehrfachtreffern() {
        let mut p = packet(1_000, 500);
        p.set_specials(vec![SpecialDamage::Critical, SpecialDamage::Back]);
        p.set_multi_hit_count(2);
        p.set_multi_hit_damage(120);
        let hit = Hit::from_packet(&p);
        assert_eq!(hit.damage, 620);
        assert_eq!(hit.multi, 2);
        assert_eq!(hit.flags, flag("crit") | flag("back"));
        p.set_dot(true);
        p.set_specials(vec![]);
        assert_eq!(Hit::from_packet(&p).flags, flag("dot"));
    }

    #[test]
    fn alte_treffer_fallen_raus() {
        let log = HitLog::new(Path::new("/nicht/benutzt"));
        log.record(&packet(0, 1));
        log.record(&packet(KEEP_MS, 2));
        log.record(&packet(KEEP_MS + 1, 3));
        let left: Vec<i32> = log.hits.lock().iter().map(|h| h.damage).collect();
        assert_eq!(left, vec![2, 3]);
    }

    #[test]
    fn haken_im_kern_meldet_jeden_treffer() {
        // Prüft den Patch patches/a2tools-on-hit.patch: ohne ihn kommt hier nichts an
        let storage = DataStorage::new();
        let log = Arc::new(HitLog::new(Path::new("/nicht/benutzt")));
        let sink = log.clone();
        storage.set_on_hit(move |p| sink.record(p));
        storage.append_damage(packet(1_000, 500));
        storage.append_damage(packet(1_400, 700));
        let seen: Vec<(i64, i32)> = log.hits.lock().iter().map(|h| (h.t, h.damage)).collect();
        assert_eq!(seen, vec![(1_000, 500), (1_400, 700)]);
    }
}
