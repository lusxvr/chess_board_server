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

# Example usage
#only execute this if this is main program




if __name__ == "__main__":
    move = "a4 c6"
    print(len(chess_move_to_vector(move)))
    initial, vector = chess_move_to_vector(move)
    print("Initial Position:", initial)
    print("Movement Vector:", vector)
