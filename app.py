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
                response = arduino.send_command(physical_command)
                if response and "OK" in response:
                    print("✅ Move executed successfully")
                else:
                    print("⚠️ Arduino didn't acknowledge the move")
            except Exception as e:
                print(f"❌ Failed to send command to Arduino: {e}")
            
            # Broadcast the updated board to all clients
            sio.emit('update_board', {
                'board': game.get_board(),
                'turn': game.get_turn(),
                'last_move': game.get_last_move()
            })
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
    while game.get_turn() == "black" and not move_detected:
        # Wait a moment between checks
        time.sleep(0.5)
        
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

def get_current_board_state():
    """Helper function to get board state matrix from Arduino"""
    try:
        # Read state from Arduino
        state_string = arduino.read_board_state()
        if state_string and len(state_string) == 36:
            return arduino.board_state_to_matrix(state_string)
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

