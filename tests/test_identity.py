import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from shapecast_linux.identity import configure_machine_identity, node_hash


class MachineIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.sys = self.base/'net'; self.sys.mkdir()
        self.root = self.base/'runtime'
        self.previous = uuid._node

    def tearDown(self):
        uuid._node = self.previous
        self.temp.cleanup()

    def adapter(self, name, address, physical=True, wireless=False, assignment=0):
        folder = self.sys/name; folder.mkdir()
        (folder/'address').write_text(address)
        (folder/'addr_assign_type').write_text(str(assignment))
        if physical: (folder/'device').mkdir()
        if wireless: (folder/'wireless').mkdir()
        return folder

    def test_uses_real_factory_ethernet_instead_of_random_node(self):
        self.adapter('bridge', '00:10:20:30:40:50', physical=False)
        self.adapter('wifi', '00:10:20:30:40:51', wireless=True)
        self.adapter('ethernet', '00:10:20:30:40:52')
        uuid._node = 0x011020304099  # Synthetic multicast fallback.
        selected = configure_machine_identity(self.root, self.sys)
        self.assertEqual(selected['interface'], 'ethernet')
        self.assertEqual(uuid.getnode(), 0x001020304052)
        self.assertEqual(selected['mac_hash'], node_hash(uuid.getnode()))
        self.assertEqual((self.root/'machine-interface.json').stat().st_mode & 0o777, 0o600)

    def test_selection_is_stable_when_another_adapter_is_added(self):
        self.adapter('ethernet', '00:10:20:30:40:52')
        before = configure_machine_identity(self.root, self.sys)
        self.adapter('aaa', '00:10:20:30:40:53')
        uuid._node = None
        after = configure_machine_identity(self.root, self.sys)
        self.assertEqual(before, after)

    def test_changed_adapter_stops_instead_of_silently_changing_code(self):
        folder = self.adapter('ethernet', '00:10:20:30:40:52')
        configure_machine_identity(self.root, self.sys)
        (folder/'address').write_text('00:10:20:30:40:53')
        with self.assertRaises(ValueError): configure_machine_identity(self.root, self.sys)

    def test_rejects_virtual_randomized_and_multicast_sources(self):
        self.adapter('bridge', '00:10:20:30:40:50', physical=False)
        self.adapter('random-wifi', '02:10:20:30:40:51', wireless=True, assignment=3)
        self.adapter('multicast', '01:10:20:30:40:52')
        with self.assertRaises(ValueError): configure_machine_identity(self.root, self.sys)
        self.assertFalse((self.root/'machine-interface.json').exists())

    def test_saved_hash_cannot_spoof_a_different_address(self):
        self.adapter('ethernet', '00:10:20:30:40:52')
        configure_machine_identity(self.root, self.sys)
        file = self.root/'machine-interface.json'
        data = json.loads(file.read_text()); data['mac_hash'] = '0'*16
        file.write_text(json.dumps(data))
        with self.assertRaises(ValueError): configure_machine_identity(self.root, self.sys)


if __name__ == '__main__': unittest.main()
