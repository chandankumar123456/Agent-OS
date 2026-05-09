use ratatui::{
    backend::Backend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};
use crate::models::LogEntry;
use crate::styles::Theme;
use std::collections::VecDeque;

pub struct LogPanel {
    pub logs: VecDeque<LogEntry>,
    pub auto_scroll: bool,
    pub scroll_offset: usize,
    pub max_lines: usize,
    pub filter: Option<String>,
}

impl LogPanel {
    pub fn new(max_lines: usize) -> Self {
        Self {
            logs: VecDeque::with_capacity(max_lines),
            auto_scroll: true,
            scroll_offset: 0,
            max_lines,
            filter: None,
        }
    }

    pub fn add_log(&mut self, entry: LogEntry) {
        self.logs.push_back(entry);
        
        // Maintain max size
        while self.logs.len() > self.max_lines {
            self.logs.pop_front();
        }
        
        // Auto-scroll to bottom
        if self.auto_scroll {
            self.scroll_to_bottom();
        }
    }

    pub fn clear(&mut self) {
        self.logs.clear();
        self.scroll_offset = 0;
    }

    pub fn scroll_up(&mut self, amount: usize) {
        self.auto_scroll = false;
        self.scroll_offset = self.scroll_offset.saturating_add(amount);
        self.clamp_scroll();
    }

    pub fn scroll_down(&mut self, amount: usize) {
        self.scroll_offset = self.scroll_offset.saturating_sub(amount);
        if self.scroll_offset == 0 {
            self.auto_scroll = true;
        }
        self.clamp_scroll();
    }

    pub fn scroll_to_top(&mut self) {
        self.auto_scroll = false;
        let filtered_count = self.filtered_logs().count();
        self.scroll_offset = filtered_count.saturating_sub(1);
    }

    pub fn scroll_to_bottom(&mut self) {
        self.auto_scroll = true;
        self.scroll_offset = 0;
    }

    pub fn toggle_auto_scroll(&mut self) {
        self.auto_scroll = !self.auto_scroll;
        if self.auto_scroll {
            self.scroll_to_bottom();
        }
    }

    pub fn page_up(&mut self, page_size: usize) {
        self.scroll_up(page_size);
    }

    pub fn page_down(&mut self, page_size: usize) {
        self.scroll_down(page_size);
    }

    fn clamp_scroll(&mut self) {
        let filtered_count = self.filtered_logs().count();
        self.scroll_offset = self.scroll_offset.min(filtered_count.saturating_sub(1));
    }

    pub fn set_filter(&mut self, filter: Option<String>) {
        self.filter = filter;
        self.scroll_offset = 0;
    }

    pub fn filtered_logs(&self) -> impl Iterator<Item = &LogEntry> {
        self.logs.iter().filter(|log| {
            if let Some(ref f) = self.filter {
                log.message.to_lowercase().contains(&f.to_lowercase()) ||
                log.level.to_lowercase().contains(&f.to_lowercase())
            } else {
                true
            }
        })
    }

    pub fn draw<B: Backend>(&self, frame: &mut Frame<B>, area: Rect, theme: &Theme, focused: bool) {
        let border_style = theme.border(focused);
        let title_style = theme.title();

        let title = if self.auto_scroll {
            " Logs ▼ ".to_string()
        } else {
            " Logs (paused) ".to_string()
        };

        let block = Block::default()
            .title(title)
            .title_style(title_style)
            .borders(Borders::ALL)
            .border_style(border_style);

        let inner = block.inner(area);
        frame.render_widget(block, area);

        let filtered: Vec<&LogEntry> = self.filtered_logs().collect();
        
        if filtered.is_empty() {
            let text = if self.filter.is_some() {
                "No logs match filter"
            } else {
                "No logs"
            };
            let paragraph = Paragraph::new(text)
                .style(Style::default().fg(theme.muted))
                .alignment(ratatui::layout::Alignment::Center);
            frame.render_widget(paragraph, inner);
            return;
        }

        // Calculate visible range
        let height = inner.height as usize;
        let total = filtered.len();
        let visible_start = total.saturating_sub(height + self.scroll_offset);
        let visible_end = total.saturating_sub(self.scroll_offset);

        let visible_logs: Vec<_> = filtered[visible_start..visible_end]
            .iter()
            .map(|log| self.format_log_line(log, theme))
            .collect();

        let text = Text::from(visible_logs);
        let paragraph = Paragraph::new(text)
            .wrap(Wrap { trim: true });

        frame.render_widget(paragraph, inner);

        // Draw scroll indicator
        if total > height {
            let scroll_percent = if self.auto_scroll {
                100
            } else {
                ((total - visible_start) * 100) / total
            };
            
            let scroll_info = format!(" {}% ", scroll_percent);
            let scroll_style = Style::default().fg(theme.muted);
            
            // Position at bottom right of inner area
            let info_area = Rect::new(
                inner.x + inner.width - scroll_info.len() as u16 - 1,
                inner.y + inner.height - 1,
                scroll_info.len() as u16,
                1,
            );
            
            frame.render_widget(
                Paragraph::new(scroll_info).style(scroll_style),
                info_area,
            );
        }
    }

    fn format_log_line(&self, log: &LogEntry, theme: &Theme) -> Line {
        let timestamp = log.timestamp.format("%H:%M:%S").to_string();
        
        let level_style = theme.log_level(&log.level);
        let level_str = format!("[{:5}]", log.level.to_uppercase());
        
        let spans = vec![
            Span::styled(timestamp, Style::default().fg(theme.muted)),
            Span::raw(" "),
            Span::styled(level_str, level_style),
            Span::raw(" "),
            Span::raw(&log.message),
        ];

        Line::from(spans)
    }
}
