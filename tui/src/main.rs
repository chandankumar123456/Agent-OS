mod app;
mod components;
mod config;
mod models;
mod styles;

use clap::Parser;
use tracing::{info, error};
use anyhow::Result;

use app::run;

#[derive(Parser)]
#[command(name = "agentos-tui")]
#[command(about = "AgentOS TUI - Real-time task monitoring dashboard")]
#[command(version = "0.1.0")]
struct Args {
    /// Supervisor host
    #[arg(long, default_value = "127.0.0.1")]
    _host: String,

    /// Supervisor port
    #[arg(short, long, default_value_t = 8080)]
    _port: u16,

    /// Refresh interval in milliseconds
    #[arg(short, long, default_value_t = 1000)]
    _refresh: u64,

    /// Enable verbose logging
    #[arg(short, long)]
    verbose: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    // Initialize tracing
    let filter = if args.verbose {
        "debug"
    } else {
        "info"
    };
    
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .init();

    info!("AgentOS TUI starting...");

    // Run the app
    if let Err(e) = run(args._host, args._port) {
        error!("Application error: {}", e);
        eprintln!("Error: {}", e);
        std::process::exit(1);
    }

    Ok(())
}
