use gizmo_nfs::{export, prelude::decompress, Tpk};
use std::{env, fs, path::PathBuf, process::ExitCode};

fn run() -> Result<(), String> {
    let mut args = env::args_os().skip(1);
    let input = PathBuf::from(args.next().ok_or("usage: ps2-tpk-exporter INPUT_TPK OUTPUT_DIR")?);
    let output = PathBuf::from(args.next().ok_or("usage: ps2-tpk-exporter INPUT_TPK OUTPUT_DIR")?);
    if args.next().is_some() {
        return Err("too many arguments".into());
    }
    let bytes = fs::read(&input).map_err(|e| format!("read {}: {e}", input.display()))?;
    let entries = Tpk::directory(&bytes).map_err(|e| format!("TPK directory: {e}"))?;
    fs::create_dir_all(&output).map_err(|e| format!("create {}: {e}", output.display()))?;
    let mut decoded = 0usize;
    let mut skipped = Vec::new();
    let mut metadata = Vec::new();
    let mut diagnostics = Vec::new();
    for entry in &entries {
        match Tpk::decode_one(&bytes, entry) {
            Ok(texture) => {
                let name = export::png_name(&texture);
                let png = export::png_bytes(&texture).map_err(|e| format!("PNG {}: {e}", name))?;
                fs::write(output.join(&name), png).map_err(|e| format!("write {}: {e}", name))?;
                metadata.push(format!(
                    "{{\"hash\":\"{:08X}\",\"name\":\"{}\",\"width\":{},\"height\":{},\"file\":\"{}\"}}",
                    texture.hash.0,
                    texture.name.replace('\\', "\\\\").replace('"', "\\\""),
                    texture.width,
                    texture.height,
                    name
                ));
                decoded += 1;
            }
            Err(error) => {
                skipped.push(format!("{:08X}: {error}", entry.hash.0));
                if diagnostics.len() < 8 {
                    let start = entry.abs_offset as usize;
                    let end = start.saturating_add(entry.size as usize);
                    let raw = bytes.get(start..end).ok_or_else(|| format!("descriptor {:08X} points outside TPK", entry.hash.0))?;
                    let decoded = decompress(raw).map_err(|e| format!("diagnostic decompress {:08X}: {e}", entry.hash.0))?;
                    let needle = entry.hash.0.to_le_bytes();
                    let occurrences: Vec<usize> = decoded.windows(4).enumerate()
                        .filter_map(|(i, w)| (w == needle).then_some(i)).take(16).collect();
                    let header_at = (entry.out_size as usize).checked_sub(entry.header_from_end as usize)
                        .and_then(|v| v.checked_add(0x88));
                    let header = header_at.and_then(|p| decoded.get(p..p + 48).map(|h| (p, h)));
                    let debug_name = header.as_ref().map(|(p, _)| {
                        let b = &decoded[p.saturating_sub(0x18)..*p];
                        String::from_utf8_lossy(b.split(|x| *x == 0).next().unwrap_or_default()).to_string()
                    }).unwrap_or_default();
                    diagnostics.push(format!(
                        "{{\\"hash\\":\\"{:08X}\\",\\"offset\\":{},\\"compressed\\":{},\\"out_size\\":{},\\"header_from_end\\":{},\\"decoded_len\\":{},\\"hash_occurrences\\":{:?},\\"header_offset\\":{},\\"debug_name\\":\\"{}\\",\\"header_hex\\":\\"{}\\",\\"tail_hex\\":\\"{}\\"}}",
                        entry.hash.0, entry.abs_offset, entry.size, entry.out_size,
                        entry.header_from_end, decoded.len(), occurrences,
                        header_at.map(|x| x.to_string()).unwrap_or_else(|| "null".into()),
                        debug_name.replace('"', "\\\\""),
                        header.map(|(_, h)| h.iter().map(|b| format!("{b:02X}")).collect::<String>()).unwrap_or_default(),
                        decoded.iter().rev().take(128).rev().map(|b| format!("{b:02X}")).collect::<String>()
                    ));
                }
            },
        }
    }
    let report = format!(
        "{{\"input_bytes\":{},\"entries\":{},\"decoded\":{},\"skipped\":[{}],\"textures\":[{}]}}\n",
        bytes.len(), entries.len(), decoded,
        skipped.iter().map(|s| format!("\"{}\"", s.replace('"', "\\\""))).collect::<Vec<_>>().join(","),
        metadata.join(",")
    );
    fs::write(output.join("texture-manifest.json"), report)
        .map_err(|e| format!("write texture manifest: {e}"))?;
    println!("TPK {}: {decoded}/{} textures decoded; {} skipped", input.display(), entries.len(), skipped.len());
    if !skipped.is_empty() {
        for item in skipped.iter().take(12) {
            println!("SKIP {item}");
        }
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}
