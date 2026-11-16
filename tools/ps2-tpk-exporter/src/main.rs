use gizmo_nfs::{export, prelude::decompress, TexFormat, Tpk};
use std::{env, fs, path::PathBuf, process::ExitCode};


fn ps2_unswizzle_p8_rgba(texture: &mut gizmo_nfs::NfsTexture) -> Result<(), String> {
    let width = texture.width as usize;
    let height = texture.height as usize;
    if width % 16 != 0 || height % 4 != 0 {
        return Err(format!("PSMT8 dimensions are not aligned: {}x{}", width, height));
    }
    let expected = width.checked_mul(height).and_then(|v| v.checked_mul(4))
        .ok_or("PSMT8 image dimensions overflow")?;
    if texture.rgba.len() != expected {
        return Err(format!("PSMT8 RGBA length {} does not match {}", texture.rgba.len(), expected));
    }
    let source = texture.rgba.clone();
    for y in 0..height {
        for x in 0..width {
            let block_location = (y & !0xF) * width + (x & !0xF) * 2;
            let swap_selector = (((y + 2) >> 2) & 1) * 4;
            let pos_y = (((y & !3) >> 1) + (y & 1)) & 7;
            let column_location = pos_y * width * 2 + ((x + swap_selector) & 7) * 4;
            let byte_num = ((y >> 1) & 1) + ((x >> 2) & 2);
            let source_pixel = block_location + column_location + byte_num;
            if source_pixel >= width * height {
                return Err(format!("PSMT8 source pixel {source_pixel} outside {}x{}", width, height));
            }
            let dst = (y * width + x) * 4;
            let src = source_pixel * 4;
            texture.rgba[dst..dst + 4].copy_from_slice(&source[src..src + 4]);
            texture.rgba[dst + 3] = (u16::from(texture.rgba[dst + 3]) * 2).min(255) as u8;
        }
    }
    Ok(())
}

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
            Ok(mut texture) => {
                let source_format = format!("{:?}", texture.source_format);
                let ps2_layout = if matches!(texture.source_format, TexFormat::P8) {
                    ps2_unswizzle_p8_rgba(&mut texture)?;
                    "PSMT8-unswizzled-alpha7-expanded"
                } else {
                    "linear"
                };
                let name = export::png_name(&texture);
                let png = export::png_bytes(&texture).map_err(|e| format!("PNG {}: {e}", name))?;
                fs::write(output.join(&name), png).map_err(|e| format!("write {}: {e}", name))?;
                metadata.push(format!(
                    "{{\"hash\":\"{:08X}\",\"name\":\"{}\",\"width\":{},\"height\":{},\"source_format\":\"{}\",\"ps2_layout\":\"{}\",\"file\":\"{}\"}}",
                    texture.hash.0,
                    texture.name.replace('\\', "\\\\").replace('"', "\\\""),
                    texture.width,
                    texture.height,
                    source_format,
                    ps2_layout,
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
                        .and_then(|v| v.checked_add(0x54));
                    let header = header_at.and_then(|p| decoded.get(p..p + 48).map(|h| (p, h)));
                    let name_hex = header_at.and_then(|p| decoded.get(p.saturating_sub(0x18)..p))
                        .map(|b| b.iter().map(|v| format!("{v:02X}")).collect::<String>())
                        .unwrap_or_default();
                    diagnostics.push(format!(
                        r#"{{"hash":"{:08X}","offset":{},"compressed":{},"out_size":{},"header_from_end":{},"decoded_len":{},"hash_occurrences":{:?},"header_offset":{},"header_hash_matches":{},"name_hex":"{}","header_hex":"{}","tail_hex":"{}"}}"#,
                        entry.hash.0, entry.abs_offset, entry.size, entry.out_size,
                        entry.header_from_end, decoded.len(), occurrences,
                        header_at.map(|x| x.to_string()).unwrap_or_else(|| "null".into()),
                        header.as_ref().map(|(_, h)| h.get(0..4).map(|v| v == needle).unwrap_or(false)).unwrap_or(false),
                        name_hex,
                        header.map(|(_, h)| h.iter().map(|b| format!("{b:02X}")).collect::<String>()).unwrap_or_default(),
                        decoded.iter().rev().take(128).rev().map(|b| format!("{b:02X}")).collect::<String>()
                    ));
                }
            },
        }
    }
    let report = format!(
        r#"{{"input_bytes":{},"entries":{},"decoded":{},"skipped":[{}],"textures":[{}],"diagnostics":[{}]}}"#,
        bytes.len(), entries.len(), decoded,
        skipped.iter().map(|s| format!("{:?}", s)).collect::<Vec<_>>().join(","),
        metadata.join(","),
        diagnostics.join(",")
    ) + "\n";
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
