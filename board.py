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

class Chess6x6:
    # Initialize 6x6 chess board
    INITIAL_BOARD = [
        ["r", "b", "q", "k", "b", "r"],
        ["p", "p", "p", "p", "p", "p"],
        [".", ".", ".", ".", ".", "."],
        [".", ".", ".", ".", ".", "."],
        ["P", "P", "P", "P", "P", "P"],
        ["R", "B", "Q", "K", "B", "R"]
    ]

    def __init__(self):
        self.board = [row[:] for row in self.INITIAL_BOARD]
        self.turn = "white"
        self.move_history = []

    def get_board(self):
        """Returns the current state of the board."""
        return self.board

    def get_turn(self):
        """Returns whose turn it is."""
        return self.turn

    def is_valid_move(self, start, end):
        """Checks if a move is valid according to chess rules."""
        x1, y1 = start
        x2, y2 = end

        # Check if coordinates are within bounds
        if not (0 <= x1 < 6 and 0 <= y1 < 6 and 0 <= x2 < 6 and 0 <= y2 < 6):
            return False

        piece = self.board[x1][y1]

        if piece == ".":
            return False  # No piece to move

        color = "white" if piece.isupper() else "black"
        if color != self.turn:
            return False  # Not your turn

        target = self.board[x2][y2]
        target_color = "white" if target.isupper() else "black" if target != "." else None

        if target_color == color:
            return False  # Cannot capture your own piece

        dx, dy = x2 - x1, y2 - y1
        piece = piece.lower()

        # Piece movements
        if piece == "p":  # Pawn
            if color == "white":
                if (dx == -1 and dy == 0 and target == ".") or (dx == -1 and abs(dy) == 1 and target_color == "black"):
                    return True
            else:  # Black
                if (dx == 1 and dy == 0 and target == ".") or (dx == 1 and abs(dy) == 1 and target_color == "white"):
                    return True

        elif piece == "r":  # Rook
            if dx == 0 or dy == 0:
                return self.is_path_clear(start, end)

        elif piece == "b":  # Bishop
            if abs(dx) == abs(dy):
                return self.is_path_clear(start, end)

        elif piece == "q":  # Queen
            if dx == 0 or dy == 0 or abs(dx) == abs(dy):
                return self.is_path_clear(start, end)

        elif piece == "k":  # King
            if abs(dx) <= 1 and abs(dy) <= 1:
                return True

        return False  # Invalid move

    def is_path_clear(self, start, end):
        """Checks if there are no obstacles between start and end."""
        x1, y1 = start
        x2, y2 = end
        dx = 1 if x2 > x1 else -1 if x2 < x1 else 0
        dy = 1 if y2 > y1 else -1 if y2 < y1 else 0

        x, y = x1 + dx, y1 + dy
        while (x, y) != (x2, y2):
            if self.board[x][y] != ".":
                return False  # There is a piece in the path
            x += dx
            y += dy
        return True

    def move(self, start, end):
        """Attempts to make a move. Returns True if successful, False otherwise."""
        if self.is_valid_move(start, end):
            x1, y1 = start
            x2, y2 = end
            # Record the move
            self.move_history.append({
                'from': start,
                'to': end,
                'piece': self.board[x1][y1],
                'captured': self.board[x2][y2] if self.board[x2][y2] != '.' else None
            })
            # Make the move
            self.board[x2][y2] = self.board[x1][y1]
            self.board[x1][y1] = "."
            self.turn = "black" if self.turn == "white" else "white"
            return True
        return False

    def get_last_move(self):
        """Returns the last move made, if any."""
        return self.move_history[-1] if self.move_history else None

# Create a global instance of the game
game = Chess6x6()


