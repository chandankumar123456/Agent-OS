use clap::{Parser, Subcommand};
use tracing::info;
use anyhow::Result;
use std::path::PathBuf;

mod commands;
mod config;
mod ipc;
mod models;

use commands::{task, daemon, desktop, config as config_cmd};
use config::Config;

#[derive(Parser)]
#[command(name = "agentos")]
#[command(about = "AgentOS - Local-native autonomous agent runtime")]
#[command(version = "0.1.0")]
#[command(author = "AgentOS Team")]
struct Cli {
    #[command(subcommand)]
    command: Commands,

    /// Enable verbose output
    #[arg(short, long, global = true)]
    verbose: bool,

    /// Output format (text, json)
    #[arg(short, long, global = true, default_value = "text")]
    output: String,

    /// Configuration file path
    #[arg(short, long, global = true)]
    config: Option<String>,
}

#[derive(Subcommand)]
enum Commands {
    /// Manage tasks (create, list, get, cancel)
    #[command(alias = "t")]
    Task {
        #[command(subcommand)]
        command: TaskCommands,
    },

    /// Manage daemon (start, stop, status, logs)
    #[command(alias = "d")]
    Daemon {
        #[command(subcommand)]
        command: DaemonCommands,
    },

    /// Control desktop automation (screenshot, click, type)
    #[command(alias = "desk")]
    Desktop {
        #[command(subcommand)]
        command: DesktopCommands,
    },

    /// Manage configuration
    #[command(alias = "cfg")]
    Config {
        #[command(subcommand)]
        command: ConfigCommands,
    },
}

#[derive(Subcommand)]
enum TaskCommands {
    /// Create and execute a new task
    #[command(alias = "c")]
    Create {
        /// Task query/instruction
        query: String,

        /// Watch task execution in real-time
        #[arg(short, long)]
        watch: bool,

        /// Maximum wait time in seconds (0 = no wait)
        #[arg(short, long, default_value = "0")]
        timeout: u64,
    },

    /// List all tasks
    #[command(alias = "ls")]
    List {
        /// Filter by status
        #[arg(short, long)]
        status: Option<String>,

        /// Maximum number of results
        #[arg(short, long, default_value = "20")]
        limit: usize,
    },

    /// Get task details
    #[command(alias = "g")]
    Get {
        /// Task ID
        id: String,
    },

    /// Cancel a running task
    #[command(alias = "cancel")]
    Cancel {
        /// Task ID
        id: String,
    },

    /// Stream task logs
    #[command(alias = "log")]
    Logs {
        /// Task ID
        id: String,

        /// Follow log output (tail -f style)
        #[arg(short, long)]
        follow: bool,

        /// Number of lines to show from the end
        #[arg(short, long, default_value = "50")]
        tail: usize,
    },
}

#[derive(Subcommand)]
enum DaemonCommands {
    /// Start the supervisor daemon
    #[command(alias = "s")]
    Start {
        /// Run in background
        #[arg(short, long)]
        background: bool,

        /// Auto-start if not running
        #[arg(long)]
        auto_start: bool,
    },

    /// Stop the supervisor daemon
    #[command(alias = "stop")]
    Stop {
        /// Force stop (kill -9)
        #[arg(short, long)]
        force: bool,
    },

    /// Check daemon status
    #[command(alias = "st")]
    Status,

    /// View daemon logs
    #[command(alias = "log")]
    Logs {
        /// Follow log output
        #[arg(short, long)]
        follow: bool,

        /// Number of lines
        #[arg(short, long, default_value = "100")]
        lines: usize,
    },

    /// Restart the daemon
    #[command(alias = "rs")]
    Restart {
        /// Force restart
        #[arg(short, long)]
        force: bool,
    },
}

#[derive(Subcommand)]
enum DesktopCommands {
    /// Take a screenshot
    #[command(alias = "ss")]
    Screenshot {
        /// Output file path
        #[arg(short, long)]
        output: Option<String>,

        /// Capture specific window by title
        #[arg(short, long)]
        window: Option<String>,
    },

    /// Click at coordinates
    #[command(alias = "clk")]
    Click {
        /// X coordinate
        #[arg(short, long)]
        x: i32,

        /// Y coordinate
        #[arg(short, long)]
        y: i32,

        /// Mouse button (left, right, middle)
        #[arg(short, long, default_value = "left")]
        button: String,

        /// Number of clicks
        #[arg(short, long, default_value = "1")]
        clicks: u32,
    },

    /// Type text
    #[command(alias = "type")]
    TypeText {
        /// Text to type
        text: String,

        /// Interval between keystrokes in ms
        #[arg(short, long, default_value = "10")]
        interval: u64,
    },

    /// Focus a window
    #[command(alias = "focus")]
    Focus {
        /// Window title (partial match)
        #[arg(short, long)]
        window: String,
    },

    /// List all open windows
    #[command(alias = "ls")]
    ListWindows {
        /// Filter by title
        #[arg(short, long)]
        filter: Option<String>,
    },

    /// Find element on screen using OCR
    #[command(alias = "find")]
    Find {
        /// Text to find
        text: String,

        /// Take screenshot and search
        #[arg(short, long)]
        screenshot: bool,
    },
}

#[derive(Subcommand)]
enum ConfigCommands {
    /// Set a configuration value
    #[command(alias = "s")]
    Set {
        /// Configuration key
        key: String,

        /// Configuration value
        value: String,
    },

    /// Get a configuration value
    #[command(alias = "g")]
    Get {
        /// Configuration key
        key: String,
    },

    /// List all configuration
    #[command(alias = "ls")]
    List,

    /// Initialize default configuration
    #[command(alias = "init")]
    Init {
        /// Force overwrite existing config
        #[arg(short, long)]
        force: bool,
    },

    /// Show configuration file path
    #[command(alias = "path")]
    Path,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialize tracing
    let filter = if cli.verbose {
        "debug"
    } else {
        "info"
    };
    
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .init();

    info!("AgentOS CLI starting...");

    // Load configuration
    let config = if let Some(config_path) = cli.config {
        Config::from_file(&PathBuf::from(config_path))?
    } else {
        Config::load_default()?
    };

    // Execute command
    match cli.command {
        Commands::Task { command } => {
            match command {
                TaskCommands::Create { query, watch, timeout } => {
                    task::create(&config, query, watch, timeout, &cli.output).await?;
                }
                TaskCommands::List { status, limit } => {
                    task::list(&config, status, limit, &cli.output).await?;
                }
                TaskCommands::Get { id } => {
                    task::get(&config, id, &cli.output).await?;
                }
                TaskCommands::Cancel { id } => {
                    task::cancel(&config, id).await?;
                }
                TaskCommands::Logs { id, follow, tail } => {
                    task::logs(&config, id, follow, tail).await?;
                }
            }
        }
        Commands::Daemon { command } => {
            match command {
                DaemonCommands::Start { background, auto_start } => {
                    daemon::start(&config, background, auto_start).await?;
                }
                DaemonCommands::Stop { force } => {
                    daemon::stop(&config, force).await?;
                }
                DaemonCommands::Status => {
                    daemon::status(&config, &cli.output).await?;
                }
                DaemonCommands::Logs { follow, lines } => {
                    daemon::logs(&config, follow, lines).await?;
                }
                DaemonCommands::Restart { force } => {
                    daemon::restart(&config, force).await?;
                }
            }
        }
        Commands::Desktop { command } => {
            match command {
                DesktopCommands::Screenshot { output, window } => {
                    desktop::screenshot(&config, output, window).await?;
                }
                DesktopCommands::Click { x, y, button, clicks } => {
                    desktop::click(&config, x, y, button, clicks).await?;
                }
                DesktopCommands::TypeText { text, interval } => {
                    desktop::type_text(&config, text, interval).await?;
                }
                DesktopCommands::Focus { window } => {
                    desktop::focus(&config, window).await?;
                }
                DesktopCommands::ListWindows { filter } => {
                    desktop::list_windows(&config, filter, &cli.output).await?;
                }
                DesktopCommands::Find { text, screenshot } => {
                    desktop::find(&config, text, screenshot).await?;
                }
            }
        }
        Commands::Config { command } => {
            match command {
                ConfigCommands::Set { key, value } => {
                    config_cmd::set(&config, key, value)?;
                }
                ConfigCommands::Get { key } => {
                    config_cmd::get(&config, key)?;
                }
                ConfigCommands::List => {
                    config_cmd::list(&config)?;
                }
                ConfigCommands::Init { force } => {
                    config_cmd::init(force)?;
                }
                ConfigCommands::Path => {
                    config_cmd::path()?;
                }
            }
        }
    }

    Ok(())
}
