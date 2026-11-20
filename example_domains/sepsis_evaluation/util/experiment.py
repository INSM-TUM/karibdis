import datetime as dt
import inspect



class SystemUnderEvaluation:
    """Abstract class for systems to be experimented upon."""

    def __init__(self, activities):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_valuations(self, log_xes, current_time):
        """
        For a given unfinished case and time, return valuations of actions to take.
        Return dict mapping from action to (valuation, reasoning), where valuation is a float and reasoning is a list of strings.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def __call__(self, *args, **kwargs):
        return self.get_valuations(*args, **kwargs)


class Experiment:
    """Wrapper for one experiment relating to one guideline."""

    created_experiments = []

    def __init__(self, system_under_eval : SystemUnderEvaluation):
        self.system_under_eval = system_under_eval
        self.correct = 0
        self.total = 0
        self.name = f'{system_under_eval.__name__ if hasattr(system_under_eval, '__name__') else system_under_eval.__class__.__name__} - {inspect.stack()[1][3]}'
        print(self.name)
        Experiment.created_experiments.append(self)

    def test(self, bool_test):
        self.total += 1
        if bool_test:
            self.correct += 1
            print('\033[92m✓\033[0m', end='')
        else:
            print('\033[91m✗\033[0m', end='')
            pass # for enabling debugging breakpoints

    def test_optional(self, bool_test):
        # self.total += 1
        if bool_test:
            # self.correct += 1
            print('\033[92m(✓)\033[0m', end='')
        else:
            print('\033[91m(✗)\033[0m', end='')
            pass # for enabling debugging breakpoints

    def results(self):
        return f'{self.name} ({len(self.low_results)}x{len(self.high_results)}x{len(self.keys)})', self.correct, self.total

    def run_system(self, builder):
        log_xes = builder.to_xes()
        current_time = builder.get_current_time()
        result = self.system_under_eval(log_xes, current_time)
        print(result)
        return result


    def test_two_classes(self, low_cases, high_cases, *keys):
        self.low_results = list(map(self.run_system, low_cases))
        self.high_results = list(map(self.run_system, high_cases))
        self.keys = keys
        for low_res in self.low_results:
            for high_res in self.high_results:
                # test_func(low_res, high_res)
                for key in keys:
                    self.test(high_res.get(key, (0, '')) > low_res.get(key, (0, '')))

        low_reasons = ['\n'.join(result.get(key, (0, ''))[1]) for result in self.low_results]
        high_reasons = ['\n'.join(result.get(key, (0, ''))[1]) for result in self.high_results]
        print('')
        for reason in low_reasons:
            print(f'\033[91m> {reason}\033[0m')
        for reason in high_reasons:
            print(f'\033[92m> {reason}\033[0m')
    
    @classmethod
    def report_all_experiments(cls):
        for experiment in cls.created_experiments:
            print(experiment.results())
        print(f'Total: {sum(experiment.correct for experiment in cls.created_experiments)} / {sum(experiment.total for experiment in cls.created_experiments)} passed over {sum(len(experiment.low_results) for experiment in cls.created_experiments)}/{sum(len(experiment.high_results) for experiment in cls.created_experiments)} A/B situations')


### Utils
class MockDateTime(dt.datetime):
    now_date = dt.datetime(2020, 1, 2, 3, 4, 2)

    @classmethod
    def set_now_date(cls, new_now_date):
        cls.now_date = new_now_date

    @classmethod
    def now(cls, timezone = None):
        return cls.now_date.replace(tzinfo=timezone)

import contextlib

@contextlib.contextmanager
def mock_time(new_now_date):
    """Allows making the system time appear as if it is a different time, for testing purposes."""
    MockDateTime.set_now_date(new_now_date)
    try:
        real_datetime_class = dt.datetime
        dt.datetime = MockDateTime
        yield None
    finally:
        dt.datetime = real_datetime_class
