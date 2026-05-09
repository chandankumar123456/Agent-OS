// Test client for gRPC bridge
// Usage: cargo run --bin test-client -- <server_address>

use desktop_automation::bridge::grpc_client::DesktopGrpcClient;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let server_addr = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "http://localhost:50051".to_string());

    println!("Connecting to gRPC server at: {}", server_addr);

    let mut client = DesktopGrpcClient::connect(&server_addr).await?;
    println!("Connected successfully!");

    // Test 1: Find a window
    println!("\n=== Test 1: Find Window ===");
    match client.find_window("", "", true).await {
        Ok(response) => {
            println!("Found window: {}", response.title);
            println!("  ID: {}", response.window_id);
            println!("  Position: ({}, {})", response.x, response.y);
            println!("  Size: {}x{}", response.width, response.height);
            println!("  Found: {}", response.found);
        }
        Err(e) => println!("Error: {}", e),
    }

    // Test 2: Observe desktop state
    println!("\n=== Test 2: Observe Desktop ===");
    match client.observe("test-session", true).await {
        Ok(response) => {
            println!("Observation ID: {}", response.observation_id);
            println!("Timestamp: {}", response.timestamp);
            println!("Window count: {}", response.window_count);
            println!("Text content length: {}", response.text_content.len());
            println!("Screenshot available: {}", response.screenshot_available);
            println!("Windows:");
            for window in &response.windows {
                println!("  - {} ({}): {}x{} at ({}, {})",
                    window.title,
                    window.id,
                    window.width,
                    window.height,
                    window.x,
                    window.y
                );
            }
        }
        Err(e) => println!("Error: {}", e),
    }

    // Test 3: Make a decision
    println!("\n=== Test 3: Make Decision ===");
    match client.decide("test-observation").await {
        Ok(response) => {
            if let Some(action) = response.action {
                println!("Action type: {}", action.action_type);
                println!("Target: {}", action.target);
                println!("Position: ({}, {})", action.x, action.y);
                println!("Text: {}", action.text);
                println!("Confidence: {}", action.confidence);
            } else {
                println!("No action decided");
            }
        }
        Err(e) => println!("Error: {}", e),
    }

    // Test 4: Close session
    println!("\n=== Test 4: Close Session ===");
    match client.close_session("test-session").await {
        Ok(response) => {
            println!("Session closed: {}", response.success);
        }
        Err(e) => println!("Error: {}", e),
    }

    println!("\n=== All tests completed ===");
    Ok(())
}
