use gizmo_nfs::{export, Tpk};
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
            Err(error) => skipped.push(format!("{:08X}: {error}", entry.hash.0)),
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
