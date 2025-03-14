import serial
import serial.tools.list_ports
import time

class ArduinoController:
    def __init__(self, baud_rate=115200):
        self.serial = None
        self.baud_rate = baud_rate
        
    def list_ports(self):
        """List all available serial ports"""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            print(f"Found port: {port.device}")
        return ports

    def connect(self, port=None):
        """
        Connect to Arduino. If no port specified, tries to find it automatically.
        """
        if port is None:
            # Try to find Arduino port automatically
            ports = list(serial.tools.list_ports.comports()) #['/dev/ttyACM0', '/dev/ttyACM1']
            for p in ports:
                # Usually Arduino shows up as "USB-SERIAL CH340" or similar
                if "USB" in p.description or "Arduino" in p.description or "ACM" in p.description:
                    port = p.device
                    print(f"Found port: {port}")
                    break
            if port is None:
                raise Exception("No Arduino found! Available ports: " + 
                              str([p.device for p in ports]))

        try:
            self.serial = serial.Serial(port, self.baud_rate, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset
            print(f"✅ Connected to Arduino on {port}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to Arduino: {e}")
            return False

    def send_command(self, command):
        """Send a command to Arduino without waiting for acknowledgment"""
        if not self.serial:
            raise Exception("Not connected to Arduino!")
        
        try:
            # Add newline to command for Arduino parsing
            command = command + '\n'
            self.serial.write(command.encode())
            
            # Just wait a short time for the command to be processed
            time.sleep(0.1)
            
            return True
        except Exception as e:
            print(f"❌ Error sending command: {e}")
            return False

    def close(self):
        """Close the serial connection"""
        if self.serial:
            self.serial.close()
            print("Connection closed")

    def read_board_state(self, verbose=False):
        """
        Read the current state of the physical board from hall effect sensors
        
        Args:
            verbose (bool): Whether to print verbose output
        """
        if not self.serial:
            raise Exception("Not connected to Arduino!")
        
        try:
            # Clear buffers and ensure connection is ready
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            if verbose:
                print("Sending READ_BOARD command to Arduino...")
            
            # Send command with proper line ending
            self.serial.write(b"READ_BOARD\n")
            self.serial.flush()
            
            # Wait for Arduino to process
            time.sleep(0.2)
            
            # Check if data is available
            available = self.serial.in_waiting
            
            if available > 0:
                # Read response
                response = self.serial.readline().decode().strip()
                
                # Check for valid response format
                if response and len(response) == 36 and all(c in '01' for c in response):
                    return response
                else:
                    if verbose:
                        print(f"Invalid board state format: '{response}', length: {len(response)}")
                    return None
            else:
                if verbose:
                    print("No data received from Arduino")
                return None
            
        except Exception as e:
            if verbose:
                print(f"Error reading board state: {e}")
            return None

    def board_state_to_matrix(self, state_string):
        """
        Convert the 36-digit string to a 6x6 matrix representation
        
        The sensors are likely arranged with A1 at index 0, not A6
        We need to remap to have A6 at (0,0) in our matrix
        """
        if not state_string or len(state_string) != 36:
            return None
        
        # First, create a temporary 6x6 matrix from the string
        # assuming the string reads from A1 (bottom-left) to F6 (top-right)
        temp_matrix = []
        for i in range(6):
            row = []
            for j in range(6):
                index = i * 6 + j
                row.append(int(state_string[index]))
            temp_matrix.append(row)
        
        # Now flip the matrix vertically to have A6 at (0,0)
        # This puts top row (rank 6) at index 0
        matrix = list(reversed(temp_matrix))
        
        return matrix

    def detect_move(self, previous_state, current_state):
        """
        Detect a move by comparing previous and current board states
        Returns move in chess notation (e.g., 'e2 e4')
        """
        if not previous_state or not current_state:
            return None
        
        # Find where pieces were removed and added
        removed = []
        added = []
        
        for i in range(6):
            for j in range(6):
                if previous_state[i][j] == 1 and current_state[i][j] == 0:
                    removed.append((i, j))
                elif previous_state[i][j] == 0 and current_state[i][j] == 1:
                    added.append((i, j))
        
        # A valid move has one removal and one addition
        if len(removed) == 1 and len(added) == 1:
            # Convert to chess notation
            # With A6 at (0,0):
            # Files: j directly maps to a-f (0=a, 1=b, 2=c, etc.)
            # Ranks: i directly maps to 6-1 (0=6, 1=5, 2=4, etc.)
            files = {0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'e', 5: 'f'}
            ranks = {0: '6', 1: '5', 2: '4', 3: '3', 4: '2', 5: '1'}
            
            from_square = f"{files[removed[0][1]]}{ranks[removed[0][0]]}"
            to_square = f"{files[added[0][1]]}{ranks[added[0][0]]}"
            
            return f"{from_square} {to_square}"
        
        # Handle captures or other special cases
        elif len(removed) == 2 and len(added) == 1:
            # ... same coordinate mapping as above ...
            pass
        
        return None

    def wait_for_move_completion(self, timeout=300):
        """Wait for the Arduino to complete a move"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.serial.in_waiting > 0:
                response = self.serial.readline().decode().strip()
                if response == "MOVE_COMPLETE":
                    return True
            time.sleep(0.1)
        return False

    def matrix_to_string(self, matrix):
        """Convert a 6x6 matrix back to a 36-character string for display"""
        if not matrix or len(matrix) != 6:
            return "Invalid matrix"
        
        result = ""
        for row in matrix:
            for cell in row:
                result += str(cell)
        
        return result