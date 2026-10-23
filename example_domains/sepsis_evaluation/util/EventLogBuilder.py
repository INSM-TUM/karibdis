from collections.abc import Mapping, Sequence
import datetime as dt
from typing import Any
import xml.etree.ElementTree as ET

TIMESTAMP = "time:timestamp"
ACTIVITY = "concept:name"
TASK_ID = "concept:instance"
TRANSITION = "lifecycle:transition"



class EventLogBuilder:
    '''
    Utility class for building XES event logs for experiments

    Example usage:
    ```
    ACTIVITY_A = "Activity A"
    ACTIVITY_B = "Activity B"
    ACTIVITY_C = "Activity C"
    
    ...

    log = (
        EventLogBuilder()
        .add_trace({NAME : "John Maynard", AGE : 68, DIAGNOSED: {DIABETES}, SUSPECTED : {SEPSIS}})
        .add_task(ACTIVITY_A).start("2024-06-02T08:05:00", {'foo' : "bar"}).complete("2024-06-02T12:10:00", {'resource' : "nurse-2"})
        .add_task(ACTIVITY_C).start("2024-06-02T10:05:00").complete("2024-06-02T10:10:00", {'resource' : "nurse-2"})
        .add_task(ACTIVITY_B).start("2024-06-02T09:05:00").complete("2024-06-02T10:06:00", {'resource' : "nurse-2"})
    )

    print(log.to_xes(log_name="sepsis_case"))
    ```
    '''

    def __init__(self) -> None:
        self._traces: list[dict[str, Any]] = []
        self._current_trace: dict[str, Any] | None = None
        self._current_activity : str | None = None
        self._current_task : str | None = None
        self._current_time : dt.datetime | None = None

    def add_trace(self, case_attributes = dict()):
        self._current_trace = {"case_attributes": case_attributes, "events": []}
        self._traces.append(self._current_trace)
        return self

    def add_task(
        self,
        activity_name: str
    ):
        if self._current_trace is None:
            raise ValueError("A trace must be added before adding activities.")

        self._current_activity = activity_name
        self._current_task = activity_name + f'_{len(self._traces)}_{len(self._current_trace['events'])}'
        
        return self

    def _event(self, timestamp, transition, attributes: Mapping[str, Any] = None):
        event: dict[str, Any] = {
            ACTIVITY : self._current_activity, 
            TASK_ID : self._current_task , 
            TIMESTAMP: dt.datetime.fromisoformat(timestamp), 
            TRANSITION : transition 
        }
        if attributes:
            event.update(attributes)
        self._current_trace["events"].append(event)
        return self

    def start(self, start_timestamp, attributes: Mapping[str, Any] = None):
        return self._event(start_timestamp, "start", attributes)

    def complete(self, end_timestamp, attributes: Mapping[str, Any] = None):
        return self._event(end_timestamp, "complete", attributes)

    def set_current_time(self, timestamp):
        self._current_time = dt.datetime.fromisoformat(timestamp)
        return self

    def get_current_time(self):
        if self._current_time is not None:
            return self._current_time
        else:
            # Latest timestamp of all events in all traces
            return max((event[TIMESTAMP] for trace in self._traces for event in trace["events"]), default=None)



    def to_xes(self, log_name: str = "example_log") -> str:
        if not self._traces:
            raise ValueError("Cannot serialize an empty event log.")
        
        log = ET.Element(
            "log",
            {
                "xes.version": "2.0",
                # "xes.features": "nested-attributes",
                # "openxes.version": "1.0RC7",
                "xmlns": "http://www.xes-standard.org/",
            },
        )
        ET.SubElement(log, "string", {"key": "concept:name", "value": str(log_name)})

        trace = self._traces[-1]
        case_values = dict(trace["case_attributes"])
        trace_name = str(case_values.get("concept:name", 'trace_1'))

        trace_xml = ET.SubElement(log, "trace")
        ET.SubElement(trace_xml, "string", {"key": "concept:name", "value": trace_name})
        for key, value in case_values.items():
            if key == "concept:name":
                continue
            _xes_element(trace_xml, key, value)

        for event in sorted(trace["events"], key=lambda x: x[TIMESTAMP]):
            event_xml = ET.SubElement(trace_xml, "event")
            for key, value in event.items():
                _xes_element(event_xml, key, value)

        ET.indent(log, space="\t", level=0)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(log, encoding="unicode")

def is_collection(obj):
    return hasattr(obj, "__iter__") and not isinstance(obj, str)

def _xes_element(parent : ET.Element, key, value):
    if is_collection(value):
        element = ET.SubElement(parent, 'list', {"key": str(key)})
        values = ET.SubElement(element, 'values')
        for subvalue in value:
            _xes_element(values, key, subvalue)
    else: 
        ET.SubElement(parent, _xes_type_name(value), {"key": str(key), "value": _xes_value(value)})

def _xes_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (dt.datetime, dt.date)):
        return "date"
    return "string"


def _xes_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dt.datetime, dt.date)):
        return value.astimezone().isoformat()
    return str(value)



