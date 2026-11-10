//! Replay: einen Mitschnitt (`packets_*.txt`, wie `--save-packets` oder das Meter ihn schreibt)
//! durch denselben Parser schicken. Ohne Port-Erkennung und ohne Prüfung auf das laufende Spiel.
//! Die Uhr ist die des Mitschnitts; DPS-Zeilen und Speichern laufen in ihrem Takt.

use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use a2tools_dps_meter_lib::capture::packet_accumulator::PacketAccumulator;
use a2tools_dps_meter_lib::capture::stream_processor::StreamProcessor;
use a2tools_dps_meter_lib::combat::ping_tracker::PingTracker;
use a2tools_dps_meter_lib::{rederive, share};

use crate::args::Args;
use crate::core::Core;
use crate::out::{Hello, Message, Out, Policy};
use crate::ticker::Ticker;
use crate::{FEATURES, HISTORY_EVERY, finish};

pub async fn run(args: Args, file: &Path) {
    let packets = match share::read_capture(file) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };
    let out = Out::spawn(std::io::stdout(), Policy::Lossless);
    let core = Core::new(&args, Arc::new(PingTracker::new()), None, out);
    core.out.send(&Message::Hello(&Hello {
        version: env!("CARGO_PKG_VERSION"),
        parser: rederive::parser_version(),
        history_dir: args.history_dir.clone(),
        features: FEATURES,
        replay: Some(file.to_path_buf()),
        packets: Some(packets.len()),
        ..Hello::default()
    }));
    let mut proc = StreamProcessor::new(core.storage.clone(), core.skills.clone(), core.npcs.clone());
    proc.set_dot_skill_ids(core.dot_ids.clone());
    let mut streams: HashMap<String, PacketAccumulator> = HashMap::new();
    let step = args.interval.as_millis() as i64;
    let save_step = HISTORY_EVERY.as_millis() as i64;
    let first = packets.first().map(|p| p.captured_at_ms).unwrap_or(0);
    let (mut next_tick, mut next_save) = (first + step, first + save_step);
    let mut ticker = Ticker::default();
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
            ticker.tick(&core);
            next_tick = p.captured_at_ms + step;
        }
        if p.captured_at_ms >= next_save {
            core.save(false);
            next_save = p.captured_at_ms + save_step;
        }
    }
    ticker.tick(&core);
    proc.set_override_timestamp(None);
    finish(&core).await;
}
