from flask import Flask, render_template, request, jsonify
import socketio
import eventlet
import converter as cv
from board import game
from arduino_controller import ArduinoController
import threading
import time

app = Flask(__name__)

# Create SocketIO server with eventlet
sio = socketio.Server(cors_allowed_origins="*")
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

# Initialize Arduino controller globally
arduino = ArduinoController()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/board', methods=['GET'])
def get_board():
    """Returns the current state of the board as JSON."""
    return jsonify({
        'board': game.get_board(),
        'turn': game.get_turn()
    })

@app.route('/move', methods=['POST'])
def make_move():
    """Handle moves from the web interface."""
    move = request.form['move'].strip()
    print(f"Move received: {move}")
    
    if len(move) == 5 and move[2] == ' ':
        start = (6 - int(move[1]), ord(move[0]) - ord('a'))
        end = (6 - int(move[4]), ord(move[3]) - ord('a'))

        if game.move(start, end):
            # Convert chess move to physical coordinates
            physical_command = cv.chess_to_physical_coords(move)
            print(f"Physical command: {physical_command}")
            
            try:
                # Send command to Arduino
                arduino.send_command(physical_command)
                print("✅ Move executed successfully")
            except Exception as e:
                print(f"❌ Failed to send command to Arduino: {e}")
            
            # Broadcast the updated board to all clients
            sio.emit('update_board', {
                'board': game.get_board(),
                'turn': game.get_turn(),
                'last_move': game.get_last_move()
            })
            
            # Debug: If this is a white move, wait 5 seconds and test Arduino communication
            if game.get_turn() == "black":
                print("\n🔍 DEBUGGING: Waiting 5 seconds to test Arduino communication...")
                
                # Add this function to directly debug Arduino communication
                def debug_arduino_communication():
                    import time
                    time.sleep(5)  # Wait 5 seconds
                    
                    print("🔍 DEBUGGING: Sending READ_BOARD command...")
                    
                    # Clear any existing data
                    arduino.serial.reset_input_buffer()
                    arduino.serial.reset_output_buffer()
                    
                    # Send command with proper line ending
                    arduino.serial.write(b"READ_BOARD\n")
                    arduino.serial.flush()
                    
                    # Wait for Arduino to process
                    time.sleep(1)
                    
                    # Check if data is available
                    available = arduino.serial.in_waiting
                    print(f"🔍 DEBUGGING: Bytes available to read: {available}")
                    
                    if available > 0:
                        # Read raw response
                        raw_response = arduino.serial.readline()
                        print(f"🔍 DEBUGGING: Raw bytes received: {raw_response}")
                        
                        # Try to decode
                        try:
                            decoded = raw_response.decode().strip()
                            print(f"🔍 DEBUGGING: Decoded response: '{decoded}'")
                            print(f"🔍 DEBUGGING: Response length: {len(decoded)}")
                        except Exception as e:
                            print(f"🔍 DEBUGGING: Error decoding response: {e}")
                    else:
                        print("🔍 DEBUGGING: No data received from Arduino")
                
                # Start debugging in a separate thread
                debug_thread = threading.Thread(target=debug_arduino_communication)
                debug_thread.daemon = True
                debug_thread.start()
                
            return jsonify({'success': True, 'board': game.get_board()})

    return jsonify({'success': False})

# WebSocket events
@sio.event
def connect(sid, environ):
    print(f"✅ Client {sid} connected")
    # Send current game state to new client
    sio.emit('update_board', {
        'board': game.get_board(),
        'turn': game.get_turn()
    }, room=sid)

@sio.event
def disconnect(sid):
    print(f"❌ Client {sid} disconnected")

@sio.on('move_from_real_board')
def handle_move(sid, data):
    """Handle moves from the physical chess board."""
    move = data['move']
    print(f"📥 Move received from client {sid}: {move}")

    if len(move) == 5 and move[2] == ' ':
        start = (6 - int(move[1]), ord(move[0]) - ord('a'))
        end = (6 - int(move[4]), ord(move[3]) - ord('a'))

        if game.move(start, end):
            print(f"✅ Move applied: {move}")
            # Broadcast the updated board to all connected clients
            sio.emit('update_board', {
                'board': game.get_board(),
                'turn': game.get_turn(),
                'last_move': game.get_last_move()
            })
            
            # If it's now black's turn, start monitoring the physical board
            if game.get_turn() == "black":
                print("👁️ Black's turn - checking physical board")
                # Start a non-blocking check (in a separate thread)
                thread = threading.Thread(target=wait_for_physical_move)
                thread.daemon = True
                thread.start()
        else:
            print("❌ Invalid move")
            sio.emit('move_rejected', {'message': 'Invalid move'}, room=sid)
    else:
        print("❌ Incorrect move format")
        sio.emit('move_rejected', {'message': 'Incorrect move format'}, room=sid)

@sio.on('update_board')
def on_board_updated(data):
    """Handle board updates - check physical board when it's Black's turn"""
    current_turn = data.get('turn')
    
    if current_turn == "black":
        # Start monitoring physical board for Black's move
        print("👁️ Black's turn - checking physical board")
        wait_for_physical_move()

def wait_for_physical_move():
    """Check the physical board until a valid move is detected"""
    # Take an initial snapshot of the board
    initial_state = get_current_board_state()
    if not initial_state:
        print("❌ Could not read initial board state")
        return
    
    print("✅ Initial board state captured, waiting for move...")
    
    # Poll until we detect a change or it's no longer Black's turn
    move_detected = False
    attempts = 0
    max_attempts = 1200  # 60 seconds at 0.5s intervals
    
    while game.get_turn() == "black" and not move_detected and attempts < max_attempts:
        # Wait a moment between checks
        time.sleep(0.5)
        attempts += 1
        
        # Read current state
        current_state = get_current_board_state()
        if not current_state:
            continue  # Skip this iteration if read failed
        
        # Check if a move was made
        move = arduino.detect_move(initial_state, current_state)
        if move:
            print(f"Detected move from physical board: {move}")
            
            # Process the move
            start = (6 - int(move[1]), ord(move[0]) - ord('a'))
            end = (6 - int(move[4]), ord(move[3]) - ord('a'))
            
            if game.move(start, end):
                print(f"✅ Move applied: {move}")
                # Broadcast the updated board to all connected clients
                sio.emit('update_board', {
                    'board': game.get_board(),
                    'turn': game.get_turn(),
                    'last_move': game.get_last_move()
                })
                move_detected = True
            else:
                print("❌ Invalid move detected from physical board")
    
    if not move_detected and game.get_turn() == "black":
        print("⚠️ Timed out waiting for physical move")

def get_current_board_state():
    """Helper function to get board state matrix from Arduino"""
    try:
        print("Requesting board state from Arduino...")
        
        # Read state from Arduino
        state_string = arduino.read_board_state()
        
        if state_string and len(state_string) == 36:
            print(f"Converting board state to matrix: {state_string}")
            return arduino.board_state_to_matrix(state_string)
        else:
            print(f"Failed to get valid board state (received: {state_string})")
            return None
    except Exception as e:
        print(f"Error reading board state: {e}")
        return None

# Modify the if __name__ == '__main__' block to start the monitoring thread
if __name__ == '__main__':
    try:
        # Connect to Arduino before starting server
        print("🔌 Connecting to Arduino...")
        arduino.connect()
        
        print("🚀 Starting server...")
        eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 5000)), app)
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Make sure to close Arduino connection when server stops
        arduino.close()

