from simulator import *
import signal

class SimulatorForDemonstration(Simulator):

    def __init__(self, **args):
        super().__init__(**args)
        self.is_paused = False

    # Run the simulation for $running_time more time
    def run(self, running_time):
        self.original_sigint_handler = signal.getsignal(signal.SIGINT)
        if self.now < float('inf'):
            self.run_until = self.now + running_time
        else:
            self.run_until = 0
            
        if self.is_paused:
            self.is_paused = False
            self.now = self.old_now
            self.old_now = None
            print(f'Resuming simulation at time {self.now}. Remaining time to run: {running_time}')
        try:
            signal.signal(signal.SIGINT, self.handle_interrupt)
            try:
                return super().run(self.run_until)
            except ZeroDivisionError:
                self.finalized_cases = -1
                return super().run(0) 
        except KeyboardInterrupt: # Fallback if signals don't work
            self.pause()
            # return super().run(0)
        finally: 
            signal.signal(signal.SIGINT, self.original_sigint_handler)

    def init_simulation(self):
        super().init_simulation()
        (_, first_task_event) = self.events[-1]
        self.events[-1] = (0, first_task_event) # Make sure at time 0 there will always be an allocation decision
            
    def handle_interrupt(self, signum, frame):
        print('Interrupt')
        if not self.is_paused:
            self.pause()
        else: 
            self.original_sigint_handler(signum, frame)
            
    # Pause the simulation by gracefully interrupting the current loop 
    def pause(self):
        if self.now < float('inf'):
            print(f'Pausing Simulation at time {self.now}. Will complete running current cycle. Interrupt again for immediate cancellation.')
            self.old_now = self.now
        else:
            print('Cancelling immediately.')
        self.now = float('inf') # Will complete running current event, then discontinue loop
        self.is_paused = True

    # Resume the simulation to run until the initially specified time
    def resume(self):
        if not self.is_paused:
            print('Simulation hasn\'t been paused!')
        else:
            self.run(self.run_until - self.old_now)
        