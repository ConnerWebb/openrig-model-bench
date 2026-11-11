import errno, json, pathlib, unittest
import os, signal
from unittest.mock import patch
import observer
from observer import Guard, temperatures, critical_sample

class FaultIsolation(unittest.TestCase):
    def test_real_sensor_error_does_not_suppress_essential_sample(self):
        sample = critical_sample()
        values, errors = temperatures()
        self.assertGreater(sample['available'], 0)
        self.assertIn('pswpout', sample)
        self.assertTrue(values)
        self.assertIsInstance(errors, dict)

    def test_sensor_eloop_and_other_bad_sensor_are_individually_retained(self):
        def read(path):
            if path == 'wifi':
                raise OSError(errno.ELOOP, 'Too many levels of symbolic links')
            return 'bad' if path == 'malformed' else '42000'
        values, errors = temperatures(['wifi', 'good', 'malformed'], read)
        self.assertEqual(values, {'good': 42000})
        self.assertEqual(errors['wifi']['errno'], errno.ELOOP)
        self.assertIn('malformed', errors)

    def test_low_memory_guard_survives_optional_sensor_failure(self):
        guard = Guard()
        self.assertIsNone(guard.check(15 * 2**30, 0, 0))
        temperatures(['wifi'], lambda p: (_ for _ in ()).throw(OSError(errno.ELOOP, 'wifi')))
        self.assertIsNone(guard.check(15 * 2**30, 0, 20))
        self.assertIn('MemAvailable', guard.check(15 * 2**30, 0, 21))

    def test_enumeration_failure_retains_sensor_error(self):
        def paths():
            yield 'first'
            raise OSError(errno.EIO, 'sensor directory changed')
        values, errors = temperatures(paths(), lambda p: '42000')
        self.assertEqual(values, {'first': 42000})
        self.assertEqual(errors['sensor-enumeration']['errno'], errno.EIO)

    def test_recovery_resets_low_memory_window(self):
        guard = Guard()
        guard.check(1, 0, 0)
        guard.check(20 * 2**30, 0, 19)
        self.assertIsNone(guard.check(1, 0, 21))
        self.assertIn('MemAvailable', guard.check(1, 0, 42))

    def test_oom_is_detected_without_requiring_low_system_memory(self):
        guard = Guard()
        self.assertIsNone(guard.check(80 * 2**30, 0, 0))
        self.assertIn('OOM', guard.check(80 * 2**30, 1, 1))

    def test_guard_signals_only_verified_campaign_command(self):
        with patch.object(pathlib.Path, 'read_bytes', return_value=b'/usr/bin/python3\0unrelated.py\0'), patch.object(observer.os, 'kill') as kill:
            with self.assertRaises(RuntimeError):
                observer.interrupt_owned(os.getpid(), 'test')
            kill.assert_not_called()
        command = b'/usr/bin/python3\0' + observer.EXPECTED_MAIN.encode() + b'\0'
        with patch.object(pathlib.Path, 'read_bytes', return_value=command), patch.object(observer, 'atomic') as save, patch.object(observer.os, 'kill') as kill:
            observer.interrupt_owned(os.getpid(), 'injected guard condition')
            save.assert_called_once()
            kill.assert_called_once_with(os.getpid(), signal.SIGTERM)

if __name__ == '__main__':
    unittest.main(verbosity=2)
