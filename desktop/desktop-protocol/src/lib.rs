// Protocol definitions for desktop automation
// This module contains gRPC service definitions and message types

pub mod desktop {
    include!("desktop_protocol.rs");
}

pub use desktop::*;
