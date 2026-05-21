use ratatui::{
    backend::Backend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Cell, Paragraph, Row, StatefulWidget, Table, TableState, Wrap},
    Frame,
};
use crate::models::{Task, TaskStatus};
use crate::styles::Theme;
use unicode_width::UnicodeWidthStr;

pub struct TaskList {
    pub tasks: Vec<Task>,
    pub state: TableState,
    pub scroll_offset: usize,
}

impl TaskList {
    pub fn new() -> Self {
        Self {
            tasks: Vec::new(),
            state: TableState::default(),
            scroll_offset: 0,
        }
    }

    pub fn update_tasks(&mut self, tasks: Vec<Task>) {
        // Preserve selection if possible
        let selected_id = self.selected_task_id();
        self.tasks = tasks;
        
        // Restore selection
        if let Some(id) = selected_id {
            if let Some(index) = self.tasks.iter().position(|t| t.id == id) {
                self.state.select(Some(index));
            }
        }
    }

    pub fn selected_task(&self) -> Option<&Task> {
        self.state.selected()
            .and_then(|idx| self.tasks.get(idx))
    }

    pub fn selected_task_id(&self) -> Option<String> {
        self.selected_task().map(|t| t.id.clone())
    }

    pub fn next(&mut self) {
        let i = match self.state.selected() {
            Some(i) => {
                if i >= self.tasks.len().saturating_sub(1) {
                    0
                } else {
                    i + 1
                }
            }
            None => 0,
        };
        self.state.select(Some(i));
    }

    pub fn previous(&mut self) {
        let i = match self.state.selected() {
            Some(i) => {
                if i == 0 {
                    self.tasks.len().saturating_sub(1)
                } else {
                    i - 1
                }
            }
            None => 0,
        };
        self.state.select(Some(i));
    }

    pub fn first(&mut self) {
        if !self.tasks.is_empty() {
            self.state.select(Some(0));
        }
    }

    pub fn last(&mut self) {
        if !self.tasks.is_empty() {
            self.state.select(Some(self.tasks.len().saturating_sub(1)));
        }
    }

    pub fn count_active(&self) -> usize {
        self.tasks.iter().filter(|t| t.status.is_active()).count()
    }

    pub fn count_completed(&self) -> usize {
        self.tasks.iter().filter(|t| matches!(t.status, TaskStatus::Completed)).count()
    }

    pub fn count_failed(&self) -> usize {
        self.tasks.iter().filter(|t| matches!(t.status, TaskStatus::Failed)).count()
    }

    pub fn draw<B: Backend>(&mut self, frame: &mut Frame<B>, area: Rect, theme: &Theme, focused: bool) {
        let border_style = theme.border(focused);
        let title_style = theme.title();

        let block = Block::default()
            .title(" Tasks ")
            .title_style(title_style)
            .borders(Borders::ALL)
            .border_style(border_style);

        let inner = block.inner(area);
        frame.render_widget(block, area);

        if self.tasks.is_empty() {
            let text = Paragraph::new("No tasks")
                .style(Style::default().fg(theme.muted))
                .alignment(ratatui::layout::Alignment::Center);
            frame.render_widget(text, inner);
            return;
        }

        // Create table
        let header_cells = [
            "Status",
            "ID",
            "Query",
            "Steps",
            "Created",
        ]
        .iter()
        .map(|h| Cell::from(*h).style(theme.header()));

        let header = Row::new(header_cells)
            .height(1)
            .bottom_margin(1);

        let rows = self.tasks.iter().map(|task| {
            let status = format!("{}", task.status);
            let id = &task.id[..8.min(task.id.len())];
            let query = truncate(&task.query, 30);
            let steps = format!("{}/{}", 
                task.steps.iter().filter(|s| matches!(s.status, crate::models::StepStatus::Completed)).count(),
                task.steps.len()
            );
            let created = format_time(&task.created_at);

            let cells = [
                Cell::from(status).style(theme.task_status(&task.status)),
                Cell::from(id).style(Style::default().fg(theme.muted)),
                Cell::from(query),
                Cell::from(steps),
                Cell::from(created).style(Style::default().fg(theme.muted)),
            ];

            Row::new(cells).height(1)
        });

        let widths = [
            Constraint::Length(12),
            Constraint::Length(10),
            Constraint::Min(20),
            Constraint::Length(8),
            Constraint::Length(12),
        ];

        let table = Table::new(rows, widths)
            .header(header)
            .highlight_style(theme.selected())
            .highlight_symbol("> ");

        frame.render_stateful_widget(table, inner, &mut self.state);
    }
}

fn truncate(s: &str, max_len: usize) -> String {
    if s.width() <= max_len {
        s.to_string()
    } else {
        let mut result = String::new();
        let mut current_len = 0;
        
        for c in s.chars() {
            let char_width = c.width().unwrap_or(1);
            if current_len + char_width + 3 > max_len {
                result.push_str("...");
                break;
            }
            result.push(c);
            current_len += char_width;
        }
        
        result
    }
}

fn format_time(dt: &chrono::DateTime<chrono::Utc>) -> String {
    let local = dt.with_timezone(&chrono::Local);
    local.format("%H:%M").to_string()
}
