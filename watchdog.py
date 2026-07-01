import time
import numpy as np

class GameWatchdog:
    def __init__(self, window_controller, stuck_threshold_seconds=4.0):
        self.window_controller = window_controller
        self.stuck_threshold = stuck_threshold_seconds
        
        self.last_position = None
        self.last_move_time = time.time()
        self.is_reconnecting = False

        self.smooth_x = 0.0
        self.smooth_y = 0.0
        self.alpha = 0.4 

    def process_anti_stuck(self, current_player_box):
        if not current_player_box:
            return False

        now = time.time()
        cx = (current_player_box[0] + current_player_box[2]) * 0.5
        cy = (current_player_box[1] + current_player_box[3]) * 0.5
        current_pos = (cx, cy)

        if self.last_position is not None:
            dist_sq = (current_pos[0] - self.last_position[0])**2 + (current_pos[1] - self.last_position[1])**2
            
            if dist_sq < 4.0:
                if now - self.last_move_time > self.stuck_threshold:
                    self.last_move_time = now
                    self.last_position = current_pos
                    return True
            else:
                self.last_move_time = now

        self.last_position = current_pos
        return False

    def apply_low_pass_filter(self, target_x, target_y):
        self.smooth_x = self.alpha * target_x + (1.0 - self.alpha) * self.smooth_x
        self.smooth_y = self.alpha * target_y + (1.0 - self.alpha) * self.smooth_y
        return self.smooth_x, self.smooth_y

    def check_disconnection(self, frame):
        return False

    def handle_reconnect(self):
        self.window_controller.press("proceed") 
        time.sleep(2)
