use std::io::Result;
use std::path::PathBuf;

fn main() -> Result<()> {
    let proto_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("proto");

    let protos: Vec<PathBuf> = vec![
        proto_dir.join("runtime.proto"),
        proto_dir.join("checkpoint.proto"),
        proto_dir.join("worker.proto"),
        proto_dir.join("desktop.proto"),
    ];

    // Verify all proto files exist
    for proto in &protos {
        if !proto.exists() {
            panic!("Proto file not found: {}", proto.display());
        }
    }

    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile(
            &protos.iter().map(|p| p.to_str().unwrap()).collect::<Vec<_>>(),
            &[
                proto_dir.to_str().unwrap(),
            ],
        )?;

    Ok(())
}
