mod app;
mod components;
mod config;
mod models;
mod styles;

use anyhow::Result;
use clap::Parser;
use tracing::{error, info};

use app::run;

#[derive(Parser)]
#[command(name = "agentos-tui")]
#[command(about = "AgentOS TUI - Real-time task monitoring dashboard")]
#[command(version = "0.1.0")]
struct Args {
    /// Enable verbose logging
    #[arg(short, long)]
    verbose: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    // Initialize tracing
    let filter = if args.verbose { "debug" } else { "info" };

    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .init();

    info!("AgentOS TUI starting...");

    // Run the app
    if let Err(e) = run() {
        error!("Application error: {}", e);
        eprintln!("Error: {}", e);
        std::process::exit(1);
    }

    Ok(())
}
