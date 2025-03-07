def chess_move_to_vector(move: str):
    # Define column and row mappings
    columns = {'a': 5, 'b': 4, 'c': 3, 'd':2, 'e': 1,'f': 0}
    rows = {'1': 0, '2': 1, '3': 2, '4': 3, '5': 4, '6': 5}
    
    # Parse the move (e.g., "a1-a2")
    start, end = move.split(' ')
    
    # Get initial coordinates
    x1, y1 = 30*columns[start[0]], 30*rows[start[1]]
    x2, y2 = 30*columns[end[0]], 30*rows[end[1]]
    
    
    return (x1, y1), (x2, y2)

def chess_to_physical_coords(chess_move):
    """
    Convert chess notation (e.g., 'e2 e4') to physical coordinates.
    Returns a string command for the Arduino: 'MOVE xs ys xe ye'
    
    Parameters:
    - Square offset from origin: 5mm
    - Square size: 30mm
    - Center offset: 15mm (half square size)
    
    Example:
    'a6' (top left in chess) -> (20, 20) in physical coordinates
    'f1' (bottom right in chess) -> (170, 170) in physical coordinates
    """
    # Split the move into start and end positions
    start_pos, end_pos = chess_move.split()
    
    def single_square_to_coords(square):
        # Convert chess notation (e.g., 'e2') to physical coordinates
        col = ord(square[0]) - ord('a')  # 'a' -> 0, 'b' -> 1, etc.
        row = 6 - int(square[1])         # '6' -> 0, '5' -> 1, etc.
        
        # Calculate physical coordinates
        # x = offset + (column * square_size) + (square_size / 2)
        # y = offset + (row * square_size) + (square_size / 2)
        x = 5 + (col * 30) + 15  # Add 15mm to reach center
        y = 5 + (row * 30) + 15  # Add 15mm to reach center
        
        return x, y
    
    # Convert both start and end positions
    start_x, start_y = single_square_to_coords(start_pos)
    end_x, end_y = single_square_to_coords(end_pos)
    
    # Format the command string
    command = f"MOVE {start_x} {start_y} {end_x} {end_y}"
    return command

# Example usage
#only execute this if this is main program




if __name__ == "__main__":
    # Example usage:
    test_moves = ['a6 a5', 'f1 f2', 'c3 d3']
    for move in test_moves:
        command = chess_to_physical_coords(move)
        print(f"Chess move: {move} -> {command}")

    # Expected output:
    # Chess move: a6 a5 -> MOVE 20 20 20 50
    # Chess move: f1 f2 -> MOVE 170 170 170 140
    # Chess move: c3 d3 -> MOVE 80 110 110 110
