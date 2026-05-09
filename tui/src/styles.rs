use ratatui::style::{Color, Modifier, Style};

pub struct Theme {
    pub background: Color,
    pub foreground: Color,
    pub primary: Color,
    pub secondary: Color,
    pub success: Color,
    pub warning: Color,
    pub error: Color,
    pub info: Color,
    pub muted: Color,
    pub highlight: Color,
    pub border: Color,
    pub border_focused: Color,
    pub header_bg: Color,
    pub header_fg: Color,
}

impl Theme {
    pub fn default() -> Self {
        Self {
            background: Color::Black,
            foreground: Color::White,
            primary: Color::Cyan,
            secondary: Color::Blue,
            success: Color::Green,
            warning: Color::Yellow,
            error: Color::Red,
            info: Color::Blue,
            muted: Color::Gray,
            highlight: Color::Magenta,
            border: Color::DarkGray,
            border_focused: Color::Cyan,
            header_bg: Color::DarkGray,
            header_fg: Color::White,
        }
    }

    pub fn task_status(&self, status: &crate::models::TaskStatus) -> Style {
        match status {
            crate::models::TaskStatus::Pending => Style::default().fg(self.muted),
            crate::models::TaskStatus::Running => Style::default().fg(self.primary).add_modifier(Modifier::BOLD),
            crate::models::TaskStatus::Paused => Style::default().fg(self.warning),
            crate::models::TaskStatus::Completed => Style::default().fg(self.success),
            crate::models::TaskStatus::Failed => Style::default().fg(self.error),
            crate::models::TaskStatus::Cancelled => Style::default().fg(self.warning),
        }
    }

    pub fn step_status(&self, status: &crate::models::StepStatus) -> Style {
        match status {
            crate::models::StepStatus::Pending => Style::default().fg(self.muted),
            crate::models::StepStatus::Running => Style::default().fg(self.primary),
            crate::models::StepStatus::Completed => Style::default().fg(self.success),
            crate::models::StepStatus::Failed => Style::default().fg(self.error),
            crate::models::StepStatus::Skipped => Style::default().fg(self.muted),
        }
    }

    pub fn log_level(&self, level: &str) -> Style {
        match level.to_lowercase().as_str() {
            "error" => Style::default().fg(self.error),
            "warn" | "warning" => Style::default().fg(self.warning),
            "info" => Style::default().fg(self.info),
            "debug" => Style::default().fg(self.muted),
            "trace" => Style::default().fg(self.muted).add_modifier(Modifier::DIM),
            _ => Style::default().fg(self.foreground),
        }
    }

    pub fn header(&self) -> Style {
        Style::default()
            .bg(self.header_bg)
            .fg(self.header_fg)
            .add_modifier(Modifier::BOLD)
    }

    pub fn selected(&self) -> Style {
        Style::default()
            .bg(self.primary)
            .fg(self.background)
            .add_modifier(Modifier::BOLD)
    }

    pub fn border(&self, focused: bool) -> Style {
        if focused {
            Style::default().fg(self.border_focused)
        } else {
            Style::default().fg(self.border)
        }
    }

    pub fn title(&self) -> Style {
        Style::default()
            .fg(self.primary)
            .add_modifier(Modifier::BOLD)
    }

    pub fn help(&self) -> Style {
        Style::default().fg(self.muted)
    }
}

pub struct Styles {
    pub theme: Theme,
}

impl Default for Styles {
    fn default() -> Self {
        Self {
            theme: Theme::default(),
        }
    }
}
