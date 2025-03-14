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

# Add a new function to continuously monitor the physical board
def monitor_physical_board():
    prev_state = None
    
    while True:
        try:
            # Only monitor when it's black's turn
            if game.get_turn() == "black":
                # Read current state from Arduino
                state_string = arduino.read_board_state()
                
                if state_string:
                    current_state = arduino.board_state_to_matrix(state_string)
                    
                    # If we have a previous state to compare with
                    if prev_state:
                        move = arduino.detect_move(prev_state, current_state)
                        
                        if move:
                            print(f"Detected move from physical board: {move}")
                            
                            # Process the move through the same handler we use for web moves
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
                                print("❌ Invalid move detected from physical board")
                    
                    # Update previous state for next comparison
                    prev_state = current_state
            
            # Wait a short time before checking again
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error monitoring physical board: {e}")
            time.sleep(1)  # Wait longer on error

# Add this before the if __name__ == '__main__' block
def start_monitor_thread():
    monitor_thread = threading.Thread(target=monitor_physical_board, daemon=True)
    monitor_thread.start()
    print("🔍 Physical board monitor started")

# Modify the if __name__ == '__main__' block to start the monitoring thread
if __name__ == '__main__':
    try:
        # Connect to Arduino before starting server
        print("🔌 Connecting to Arduino...")
        arduino.connect()
        
        # Start physical board monitoring
        start_monitor_thread()
        
        print("🚀 Starting server...")
        eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 5000)), app)
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Make sure to close Arduino connection when server stops
        arduino.close()

