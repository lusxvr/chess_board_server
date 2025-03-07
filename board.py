import socketio

# Connection to Flask-SocketIO server
sio = socketio.Client()

try:
    sio.connect('http://localhost:5000')
    print("🔌 Connected to Flask-SocketIO server")
    
    while True:
        move = input("📝 Enter your move (ex: d5 d4): ").strip()

        if len(move) == 5 and move[2] == ' ':
            print(f"📤 Sending move: {move}")
            sio.emit('move_from_real_board', {'move': move})
        else:
            print("❌ Incorrect format! Use the format: d5 d4")

except Exception as e:
    print(f"❌ Error: {e}")

finally:
    sio.disconnect()
    print("🔌 Disconnected from server")


