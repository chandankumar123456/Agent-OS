use ratatui::{
    backend::Backend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Cell, Paragraph, Row, Table, Wrap},
    Frame,
};
use crate::models::Task;
use crate::styles::Theme;

pub struct TaskDetail {
    pub visible: bool,
}

impl TaskDetail {
    pub fn new() -> Self {
        Self {
            visible: false,
        }
    }

    pub fn show(&mut self) {
        self.visible = true;
    }

    pub fn hide(&mut self) {
        self.visible = false;
    }

    pub fn toggle(&mut self) {
        self.visible = !self.visible;
    }

    pub fn draw<B: Backend>(&self, frame: &mut Frame<B>, area: Rect, theme: &Theme, task: Option<&Task>) {
        if !self.visible || task.is_none() {
            return;
        }

        let task = task.unwrap();
        let block = Block::default()
            .title(" Task Details ")
            .title_style(theme.title())
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme.border_focused));

        let inner = block.inner(area);
        frame.render_widget(block, area);

        // Create content
        let mut text = Text::default();

        // Basic info
        text.extend(vec![
            Line::from(vec![
                Span::styled("ID: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(&task.id),
            ]),
            Line::from(vec![
                Span::styled("Query: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(&task.query),
            ]),
            Line::from(vec![
                Span::styled("Status: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::styled(
                    format!("{}", task.status),
                    theme.task_status(&task.status),
                ),
            ]),
            Line::from(vec![
                Span::styled("Created: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(task.created_at.to_rfc3339()),
            ]),
            Line::from(vec![
                Span::styled("Updated: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(task.updated_at.to_rfc3339()),
            ]),
        ]);

        if let Some(ref completed) = task.completed_at {
            text.push_line(Line::from(vec![
                Span::styled("Completed: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(completed.to_rfc3339()),
            ]));
        }

        text.push_line(Line::raw(""));

        // Steps
        if !task.steps.is_empty() {
            text.push_line(Line::styled("Steps:", Style::default().add_modifier(Modifier::BOLD)));
            
            for (i, step) in task.steps.iter().enumerate() {
                let status_icon = match step.status {
                    crate::models::StepStatus::Pending => "○",
                    crate::models::StepStatus::Running => "▶",
                    crate::models::StepStatus::Completed => "✓",
                    crate::models::StepStatus::Failed => "✗",
                    crate::models::StepStatus::Skipped => "⊘",
                };

                text.push_line(Line::from(vec![
                    Span::styled(
                        format!("  {} ", status_icon),
                        theme.step_status(&step.status),
                    ),
                    Span::styled(
                        format!("{}: ", i + 1),
                        Style::default().fg(theme.muted),
                    ),
                    Span::raw(&step.description),
                ]));
            }
            
            text.push_line(Line::raw(""));
        }

        // Result or error
        if let Some(ref result) = task.result {
            text.push_line(Line::styled("Result:", Style::default().add_modifier(Modifier::BOLD)));
            text.push_line(Line::styled(result, Style::default().fg(theme.success)));
        }

        if let Some(ref error) = task.error {
            text.push_line(Line::styled("Error:", Style::default().add_modifier(Modifier::BOLD)));
            text.push_line(Line::styled(error, Style::default().fg(theme.error)));
        }

        let paragraph = Paragraph::new(text)
            .wrap(Wrap { trim: true })
            .scroll((0, 0));

        frame.render_widget(paragraph, inner);
    }
}
