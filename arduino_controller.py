import serial
import serial.tools.list_ports
import time

class ArduinoController:
    def __init__(self, baud_rate=9600):
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
            ports = ['/dev/ttyACM0', '/dev/ttyACM1'] #list(serial.tools.list_ports.comports())
            # for p in ports:
            #     # Usually Arduino shows up as "USB-SERIAL CH340" or similar
            #     if "USB" in p.description or "Arduino" in p.description:
            #         port = p.device
            #         break
            # if port is None:
            #     raise Exception("No Arduino found! Available ports: " + 
            #                   str([p.device for p in ports]))

        try:
            self.serial = serial.Serial(port, self.baud_rate, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset
            print(f"✅ Connected to Arduino on {port}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to Arduino: {e}")
            return False

    def send_command(self, command):
        """Send a command to Arduino and wait for acknowledgment"""
        if not self.serial:
            raise Exception("Not connected to Arduino!")
        
        try:
            # Add newline to command for Arduino parsing
            command = command + '\n'
            self.serial.write(command.encode())
            
            # Wait for acknowledgment from Arduino
            response = self.serial.readline().decode().strip()
            print(f"Arduino response: {response}")
            return response
        except Exception as e:
            print(f"❌ Error sending command: {e}")
            return None

    def close(self):
        """Close the serial connection"""
        if self.serial:
            self.serial.close()
            print("Connection closed")