//! Live-Mitschnitt: libpcap auf allen Interfaces (mit Kernel-Filter) → CaptureDispatcher
//! (Port-Erkennung, Reassembly, Parser) → DataStorage → DpsCalculator, wie `app.rs` im Meter.
//!
//! Rechte: Mitschneiden braucht `cap_net_raw` (`sudo setcap cap_net_raw=ep deckbar-capture`),
//! root nicht. Pakete wertet der Kern nur aus, solange AION2.exe läuft.

use std::sync::Arc;
use std::sync::atomic::Ordering;
use std::time::Duration;

use a2tools_dps_meter_lib::capture::captured_payload::CapturedPayload;
use a2tools_dps_meter_lib::capture::combat_port_detector::CombatPortDetector;
use a2tools_dps_meter_lib::capture::pcap_capturer::PcapCapturer;
use a2tools_dps_meter_lib::combat::capture_dispatcher::CaptureDispatcher;
use a2tools_dps_meter_lib::combat::ping_tracker::PingTracker;
use a2tools_dps_meter_lib::{logging, platform, rederive};
use tokio::sync::mpsc;
use tracing::{info, warn};

use crate::args::Args;
use crate::commands;
use crate::core::Core;
use crate::feed;
use crate::game;
use crate::out::{Hello, Message, Out, Policy, Status};
use crate::ticker::Ticker;
use crate::{FEATURES, HISTORY_EVERY, finish};

/// Pakete zwischen Mitschnitt und Parser (wie im Meter)
const PACKET_QUEUE: usize = 4096;

pub async fn run(args: Args) {
    let out = Out::spawn(std::io::stdout(), Policy::Live);
    let ping = Arc::new(PingTracker::with_perf_clock(platform::clock::perf_clock()));
    let ports = Arc::new(CombatPortDetector::new());
    let core = Core::new(&args, ping.clone(), Some(ports.clone()), out);
    if let Some(dev) = &args.device {
        ports.set_preferred_device(Some(dev.clone()));
    }
    if let Some(dir) = &args.save_packets {
        let _ = std::fs::create_dir_all(dir);
        logging::logger::set_packet_log_enabled(true, dir);
        info!("Pakete werden nach {} geschrieben", dir.display());
    }
    let capturing = say_hello(&core, &args);

    let (tx, rx) = mpsc::channel::<CapturedPayload>(PACKET_QUEUE);
    if capturing.0 {
        PcapCapturer::new(tx, ports.clone()).start();
    }
    let mut dispatcher =
        CaptureDispatcher::new(core.storage.clone(), core.skills.clone(), core.npcs.clone(), ports.clone(), ping);
    dispatcher.set_dot_skill_ids(core.dot_ids.clone());
    dispatcher.use_suspend_flag(core.suspended.clone());
    tokio::spawn(async move { dispatcher.run(rx).await });
    let stdin_done = tokio::spawn(commands::read_stdin(core.clone()));
    tokio::spawn(feed::watch(core.storage.clone(), core.out.clone()));
    tokio::spawn(dps_lines(core.clone(), args.interval));
    tokio::spawn(status_lines(core.clone(), ports, capturing.0 && capturing.1));
    tokio::spawn(save_regularly(core.clone()));

    // Ende: Daemon schließt stdin oder schickt SIGTERM. Vorher alles speichern.
    tokio::select! {
        _ = shutdown_signal() => {}
        _ = stdin_done => info!("stdin geschlossen"),
    }
    finish(&core).await;
}

/// Gruß; zurück: (libpcap da, cap_net_raw da).
fn say_hello(core: &Core, args: &Args) -> (bool, bool) {
    let pcap = platform::pcap::library_available();
    let caps = platform::admin::is_admin();
    if !pcap {
        warn!("libpcap nicht gefunden, kein Mitschnitt");
    }
    if !caps {
        warn!("ohne cap_net_raw: sudo setcap cap_net_raw=ep {}", std::env::current_exe().unwrap_or_default().display());
    }
    core.out.send(&Message::Hello(&Hello {
        version: env!("CARGO_PKG_VERSION"),
        parser: rederive::parser_version(),
        history_dir: args.history_dir.clone(),
        features: FEATURES,
        pcap: Some(pcap),
        cap_net_raw: Some(caps),
        ..Hello::default()
    }));
    (pcap, caps)
}

/// DPS-Zeilen im Takt `--interval-ms`, gerechnet außerhalb der Ereignisschleife.
async fn dps_lines(core: Arc<Core>, every: Duration) {
    let mut interval = tokio::time::interval(every);
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut ticker = Ticker::default();
    loop {
        interval.tick().await;
        let c = core.clone();
        ticker = tokio::task::spawn_blocking(move || {
            ticker.tick(&c);
            ticker
        })
        .await
        .unwrap_or_default();
    }
}

async fn status_lines(core: Arc<Core>, ports: Arc<CombatPortDetector>, capturing: bool) {
    let mut last = None;
    loop {
        let status = Status {
            capturing,
            game: core.game.title().is_some(),
            port: ports.current_port(),
            device: ports.current_device(),
            ping: core.ping.current_ping_ms(),
            dungeon: core.storage.current_dungeon_id(),
            local_id: core.storage.local_player_id(),
            suspended: core.suspended.load(Ordering::SeqCst),
        };
        if last.as_ref() != Some(&status) {
            core.out.send(&Message::Status(&status));
            last = Some(status);
        }
        tokio::time::sleep(game::FRESH).await;
    }
}

async fn save_regularly(core: Arc<Core>) {
    loop {
        tokio::time::sleep(HISTORY_EVERY).await;
        let c = core.clone();
        let _ = tokio::task::spawn_blocking(move || c.save(false)).await;
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
