//! deckbar-capture: AION-2-Mitschnitt für die NexBoard.
//!
//! Setzt den Kern des A2Tools DPS Meter (GPL-3.0, Submodul `a2tools/`) ohne dessen Oberfläche
//! zusammen (core.rs). Der Daemon startet das Programm und spricht mit ihm über Zeilen-JSON:
//!
//!   stdout  Nachrichten (out.rs): hello, dps, dps_data, status, fights_saved, reply, bye,
//!           plugin_frame, plugin_character, plugin_feed, frame. Ein Schreib-Thread, der Mitschnitt
//!           wartet nie auf den Daemon.
//!   stdin   Befehle (commands.rs), je Zeile `{"id":1,"cmd":"…",…}`
//!   stderr  Log (RUST_LOG, Standard: warn, für dieses Programm info)
//!
//! `dps` kommt höchstens alle `--interval-ms` und nur bei Änderung, `status` bei Änderung (ticker.rs,
//! live.rs). Nach `{"cmd":"view","full":true}` kommt zusätzlich `dps_data` (DpsData des Meters mit
//! Skill-Aufschlüsselung, bis ~100 KB), nur wenn sie sich geändert hat.
//! Kampf-History: alle 30 s, vor jedem Zurücksetzen der Kampfdaten (Zonenwechsel …) und beim
//! Beenden, als `<history-dir>/history/<id>.json` im Format des Meters, dazu die Einzeltreffer
//! als `<history-dir>/hits/<id>.json` (hits.rs).

use std::sync::Arc;
use std::time::Duration;

mod args;
mod commands;
mod core;
mod decoders;
mod effects;
mod feed;
mod frames;
mod game;
mod hits;
mod identity;
mod live;
mod out;
mod proto_gen;
mod replay;
mod ticker;
mod view;

/// So oft landen laufende Bosskämpfe in der History
pub const HISTORY_EVERY: Duration = Duration::from_secs(30);
/// Was der Daemon voraussetzen darf: "party" = Zeilen tragen das Gruppen-Flag (view.rs),
/// "dps_data" = die volle DpsData kommt als eigene Zeile
pub const FEATURES: &[&str] = &["party", "dps_data"];
/// So lange darf das letzte Schreiben beim Beenden dauern; liest der Daemon nicht mehr, endet es trotzdem
const FINAL_FLUSH: Duration = Duration::from_secs(3);

/// Ende: alles speichern, verabschieden, warten, bis die Zeilen beim Daemon sind.
pub async fn finish(core: &Arc<core::Core>) {
    let c = core.clone();
    let _ = tokio::task::spawn_blocking(move || c.save(true)).await;
    core.out.send(&out::Message::Bye);
    core.out.flush(FINAL_FLUSH);
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
    let args = args::Args::parse();
    if !args.data_dir.join("i18n").join("skills").exists() {
        eprintln!("Datenordner fehlt oder unvollständig: {} (--data)", args.data_dir.display());
        std::process::exit(1);
    }
    match args.replay.clone() {
        Some(file) => replay::run(args, &file).await,
        None => live::run(args).await,
    }
    // Alles gespeichert und verabschiedet. Tokio würde beim Beenden auf den Thread warten, der stdin
    // liest; kommt SIGTERM bei offenem stdin, endet der nie.
    std::process::exit(0);
}
