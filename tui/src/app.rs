use std::io;
use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Alignment, Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
    Terminal,
};

use crate::models::{DaemonStatus, LogEntry, Task};

pub struct App {
    pub _tasks: Vec<Task>,
    pub _logs: Vec<LogEntry>,
    pub status: DaemonStatus,
    pub connected: bool,
    pub should_quit: bool,
    pub show_help: bool,
    host: String,
    port: u16,
}

impl App {
    pub fn new(host: String, port: u16) -> Self {
        Self {
            _tasks: Vec::new(),
            _logs: Vec::new(),
            status: DaemonStatus {
                running: false,
                pid: None,
                version: "0.1.0".to_string(),
                uptime_seconds: None,
                active_tasks: 0,
                total_tasks: 0,
                memory_usage_mb: None,
                last_health_check: None,
            },
            connected: false,
            should_quit: false,
            show_help: false,
            host,
            port,
        }
    }

    fn check_connection(&self) -> bool {
        let addr: SocketAddr = format!("{}:{}", self.host, self.port)
            .parse()
            .unwrap_or_else(|_| SocketAddr::from(([127, 0, 0, 1], 8080)));
        TcpStream::connect_timeout(&addr, Duration::from_secs(2)).is_ok()
    }

    pub fn on_key(&mut self, key: KeyCode) {
        match key {
            KeyCode::Char('q') | KeyCode::Esc => self.should_quit = true,
            KeyCode::Char('?') | KeyCode::Char('/') | KeyCode::Char('h') => self.show_help = !self.show_help,
            _ => {}
        }
    }

    pub fn draw(&mut self, frame: &mut ratatui::Frame) {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .margin(1)
            .constraints([
                Constraint::Min(10),
                Constraint::Length(3),
            ])
            .split(frame.size());

        // Draw main content
        let content = if self.show_help {
            self.draw_help()
        } else {
            self.draw_dashboard()
        };
        frame.render_widget(content, chunks[0]);

        // Draw status bar
        let status = self.draw_status_bar();
        frame.render_widget(status, chunks[1]);
    }

    fn draw_dashboard(&self) -> Paragraph<'_> {
        let text = vec![
            Line::from(vec![
                Span::styled("AgentOS TUI - Real-time Monitoring", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::raw("Connection: "),
                if self.connected {
                    Span::styled("● Connected", Style::default().fg(Color::Green))
                } else {
                    Span::styled("● Disconnected", Style::default().fg(Color::Red))
                },
            ]),
            Line::from(""),
            Line::from(vec![
                Span::raw("Active Tasks: "),
                Span::styled(self.status.active_tasks.to_string(), Style::default().fg(Color::Yellow)),
            ]),
            Line::from(vec![
                Span::raw("Total Tasks: "),
                Span::raw(self.status.total_tasks.to_string()),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::raw("Press "),
                Span::styled("?", Style::default().fg(Color::Yellow)),
                Span::raw(" for help, "),
                Span::styled("q", Style::default().fg(Color::Yellow)),
                Span::raw(" to quit"),
            ]),
        ];

        Paragraph::new(text)
            .block(Block::default().borders(Borders::ALL).title("Dashboard"))
            .wrap(Wrap { trim: true })
    }

    fn draw_help(&self) -> Paragraph<'_> {
        let text = vec![
            Line::from(vec![
                Span::styled("Keyboard Shortcuts", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled("q", Style::default().fg(Color::Yellow)),
                Span::raw(" - Quit"),
            ]),
            Line::from(vec![
                Span::styled("?", Style::default().fg(Color::Yellow)),
                Span::raw(" - Toggle this help"),
            ]),
            Line::from(vec![
                Span::styled("r", Style::default().fg(Color::Yellow)),
                Span::raw(" - Refresh data"),
            ]),
        ];

        Paragraph::new(text)
            .block(Block::default().borders(Borders::ALL).title("Help"))
    }

    fn draw_status_bar(&self) -> Paragraph<'_> {
        let status_text = format!(
            " {} | v{} | {} active / {} total ",
            if self.connected { "● connected" } else { "● disconnected" },
            self.status.version,
            self.status.active_tasks,
            self.status.total_tasks
        );

        Paragraph::new(status_text)
            .style(Style::default().fg(Color::White).bg(Color::Blue))
            .alignment(Alignment::Center)
    }
}

pub fn run(host: String, port: u16) -> io::Result<()> {
    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;

    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Create app
    let mut app = App::new(host, port);

    // Main loop
    let tick_rate = std::time::Duration::from_millis(250);
    let mut last_tick = std::time::Instant::now();

    loop {
        // Draw
        terminal.draw(|f| app.draw(f))?;

        // Handle events
        let timeout = tick_rate
            .checked_sub(last_tick.elapsed())
            .unwrap_or_else(|| std::time::Duration::from_secs(0));

        if crossterm::event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                app.on_key(key.code);
            }
        }

        // Tick — check supervisor connection
        if last_tick.elapsed() >= tick_rate {
            app.connected = app.check_connection();
            last_tick = std::time::Instant::now();
        }

        // Check quit
        if app.should_quit {
            break;
        }
    }

    // Cleanup
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    Ok(())
}
