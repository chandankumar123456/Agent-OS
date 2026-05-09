use ratatui::{
    backend::Backend,
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Paragraph},
    Frame,
};
use crate::models::DaemonStatus;
use crate::styles::Theme;

pub struct StatusBar {
    pub connected: bool,
    pub status: Option<DaemonStatus>,
}

impl StatusBar {
    pub fn new() -> Self {
        Self {
            connected: false,
            status: None,
        }
    }

    pub fn update(&mut self, connected: bool, status: Option<DaemonStatus>) {
        self.connected = connected;
        self.status = status;
    }

    pub fn draw<B: Backend>(&self, frame: &mut Frame<B>, area: Rect, theme: &Theme) {
        let mut spans = vec![];

        // Connection status
        let (conn_icon, conn_style) = if self.connected {
            ("●", Style::default().fg(theme.success))
        } else {
            ("●", Style::default().fg(theme.error))
        };
        spans.push(Span::styled(conn_icon, conn_style));
        spans.push(Span::raw(" "));
        spans.push(Span::styled(
            if self.connected { "connected" } else { "disconnected" },
            conn_style,
        ));

        if let Some(ref status) = self.status {
            // Running status
            spans.push(Span::raw(" | "));
            if status.running {
                spans.push(Span::styled("running", Style::default().fg(theme.success)));
            } else {
                spans.push(Span::styled("stopped", Style::default().fg(theme.error)));
            }

            // Version
            spans.push(Span::raw(" | v"));
            spans.push(Span::styled(&status.version, Style::default().fg(theme.primary)));

            // Uptime
            if let Some(uptime) = status.uptime_seconds {
                spans.push(Span::raw(" | "));
                spans.push(Span::raw(format_uptime(uptime)));
            }

            // Tasks
            spans.push(Span::raw(" | "));
            spans.push(Span::styled(
                format!("{} active", status.active_tasks),
                Style::default().fg(theme.primary),
            ));
            spans.push(Span::raw(" / "));
            spans.push(Span::raw(format!("{} total", status.total_tasks)));

            // Memory
            if let Some(memory) = status.memory_usage_mb {
                spans.push(Span::raw(" | "));
                spans.push(Span::raw(format!("{:.1} MB", memory)));
            }
        }

        // Help hint
        let help_text = "? for help";
        let help_style = Style::default().fg(theme.muted);

        // Calculate positions
        let line = Line::from(spans);
        let help_span = Span::styled(help_text, help_style);
        
        // Create status text
        let text = line.spans.iter().map(|s| s.content.to_string()).collect::<String>();
        let help_offset = area.width.saturating_sub(help_text.len() as u16 + 2) as usize;
        
        // Combine everything
        let mut final_spans = line.spans.clone();
        
        // Add spaces to position help text
        let text_len = text.len();
        if text_len < help_offset {
            let spaces_needed = help_offset - text_len;
            final_spans.push(Span::raw(" ".repeat(spaces_needed)));
        }
        
        final_spans.push(Span::raw("  "));
        final_spans.push(help_span);

        let paragraph = Paragraph::new(Line::from(final_spans));
        frame.render_widget(paragraph, area);
    }
}

fn format_uptime(seconds: u64) -> String {
    let days = seconds / 86400;
    let hours = (seconds % 86400) / 3600;
    let minutes = (seconds % 3600) / 60;
    let secs = seconds % 60;

    if days > 0 {
        format!("{}d {}h {}m", days, hours, minutes)
    } else if hours > 0 {
        format!("{}h {}m {}s", hours, minutes, secs)
    } else if minutes > 0 {
        format!("{}m {}s", minutes, secs)
    } else {
        format!("{}s", secs)
    }
}
