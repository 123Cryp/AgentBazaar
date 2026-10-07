import json
from genlayer import *


class FakeAgentTrust(gl.Contract):
    records: TreeMap[str, str]

    @gl.public.write
    def put(self, agreement_id: str, record_json: str) -> str:
        self.records[agreement_id] = record_json
        return agreement_id

    @gl.public.view
    def get_agreement(self, agreement_id: str) -> dict:
        raw = self.records.get(agreement_id)
        if raw is None:
            raise Exception("unknown agreement_id: " + agreement_id)
        return json.loads(raw)
