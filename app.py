from flask import Flask, render_template, request, jsonify
import socketio
import eventlet

app = Flask(__name__)

# Création du serveur SocketIO avec eventlet
sio = socketio.Server(cors_allowed_origins="*")
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

# Initialisation du plateau d'échecs 6x6
INITIAL_BOARD = [
    ["r", "b", "q", "k", "b", "r"],
    ["p", "p", "p", "p", "p", "p"],
    [".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", "."],
    ["P", "P", "P", "P", "P", "P"],
    ["R", "B", "Q", "K", "B", "R"]
]

class Chess6x6:
    def __init__(self):
        self.board = [row[:] for row in INITIAL_BOARD]
        self.turn = "white"


    def is_valid_move(self, start, end):
        """Vérifie si un mouvement est valide selon les règles des échecs."""
        x1, y1 = start
        x2, y2 = end
        piece = self.board[x1][y1]

        if piece == ".":
            return False  # Aucune pièce à déplacer

        color = "white" if piece.isupper() else "black"
        if color != self.turn:
            return False  # Pas ton tour

        target = self.board[x2][y2]
        target_color = "white" if target.isupper() else "black" if target != "." else None

        if target_color == color:
            return False  # On ne peut pas capturer sa propre pièce

        dx, dy = x2 - x1, y2 - y1
        piece = piece.lower()

        # Déplacements des pièces
        if piece == "p":  # Pion
            if color == "white":
                if (dx == -1 and dy == 0 and target == ".") or (dx == -1 and abs(dy) == 1 and target_color == "black"):
                    return True
            else:  # Noir
                if (dx == 1 and dy == 0 and target == ".") or (dx == 1 and abs(dy) == 1 and target_color == "white"):
                    return True

        elif piece == "r":  # Tour
            if dx == 0 or dy == 0:
                return self.is_path_clear(start, end)

        elif piece == "b":  # Fou
            if abs(dx) == abs(dy):
                return self.is_path_clear(start, end)

        elif piece == "q":  # Dame
            if dx == 0 or dy == 0 or abs(dx) == abs(dy):
                return self.is_path_clear(start, end)

        elif piece == "k":  # Roi
            if abs(dx) <= 1 and abs(dy) <= 1:
                return True

        return False  # Mouvement invalide

    def is_path_clear(self, start, end):
        """Vérifie s'il n'y a pas d'obstacle entre start et end."""
        x1, y1 = start
        x2, y2 = end
        dx = 1 if x2 > x1 else -1 if x2 < x1 else 0
        dy = 1 if y2 > y1 else -1 if y2 < y1 else 0

        x, y = x1 + dx, y1 + dy
        while (x, y) != (x2, y2):
            if self.board[x][y] != ".":
                return False  # Il y a une pièce sur le chemin
            x += dx
            y += dy
        return True

    def move(self, start, end):
        if self.is_valid_move(start, end):
            x1, y1 = start
            x2, y2 = end
            self.board[x2][y2] = self.board[x1][y1]
            self.board[x1][y1] = "."
            self.turn = "black" if self.turn == "white" else "white"
            return True
        return False

chess_game = Chess6x6()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/board', methods=['GET'])
def get_board():
    """Renvoie l'état actuel du plateau sous forme de JSON."""
    return jsonify({'board': chess_game.board})

@app.route('/move', methods=['POST'])
def make_move():
    move = request.form['move'].strip()
    print(f"Déplacement reçu : {move}")

    if len(move) == 5 and move[2] == ' ':
        start = (6 - int(move[1]), ord(move[0]) - ord('a'))
        end = (6 - int(move[4]), ord(move[3]) - ord('a'))

        if chess_game.move(start, end):
            sio.emit('update_board', {'board': chess_game.board})  # Mettre à jour le plateau en temps réel
            return jsonify({'success': True, 'board': chess_game.board})

    return jsonify({'success': False})

# WebSocket events
@sio.event
def connect(sid, environ):
    print(f"✅ Client {sid} connecté")

@sio.event
def disconnect(sid):
    print(f"❌ Client {sid} déconnecté")

@sio.on('move_from_real_board')
def handle_move(sid, data):
    move = data['move']
    print(f"📥 Coup reçu du client {sid} : {move}")

    if len(move) == 5 and move[2] == ' ':
        start = (6 - int(move[1]), ord(move[0]) - ord('a'))
        end = (6 - int(move[4]), ord(move[3]) - ord('a'))

        if chess_game.move(start, end):
            print(f"✅ Coup appliqué : {move}")
            sio.emit('update_board', {'board': chess_game.board})  # Envoi du nouvel état du plateau
        else:
            print("❌ Coup invalide")
    else:
        print("❌ Format de coup incorrect")

# Lancer le serveur avec eventlet
if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 5000)), app)
