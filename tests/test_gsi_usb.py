import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from serve_gsi_usb import REFERENCE, init_policy_observations, read_packet, serve, transcript, verify_first_stage, verify_image, verify_mount
from record_m1_vendor import policy_result


class GsiUsbTests(unittest.TestCase):
    def test_policy_return_is_bound_to_the_open_fd_and_full_write(self):
        opening = 'policy_open_entry path=/sys/fs/selinux/load watchdog_seconds=30'
        rows = [opening, 'policy_open_rc=4', 'policy_write_entry fd=4 count=703220']
        self.assertEqual(policy_result([opening, 'policy_open_rc=-13'])['errno'], 13)
        self.assertEqual(policy_result(rows)['status'], 'UNOBSERVED')
        for rc, status, error in [(703220, 'PASS', None), (-22, 'FAIL', 22), (8, 'FAIL', None)]:
            with self.subTest(rc=rc):
                result = policy_result(rows + [f'policy_write_rc={rc} count=703220'])
                self.assertEqual((result['status'], result['errno']), (status, error))
        with self.assertRaises(ValueError):
            policy_result([opening, 'policy_open_rc=5', rows[2], 'policy_write_rc=703220 count=703220'])

    def test_live_policy_events_survive_disconnect_while_serving_image(self):
        class Console:
            def __init__(self):
                self.rows = iter((b'M1EVENT policy_write_', b'entry fd=7 count=12\n',
                                  b'GSI17 READ 0 512\n', b'M1EVENT policy_write_rc=-22 count=12\n'))
                self.writes = []

            def read_until(self, delimiter):
                try:
                    return next(self.rows)
                except StopIteration:
                    raise OSError('disconnected')

            def write(self, data):
                self.writes.append(data)
                return len(data)

        console, events = Console(), io.BytesIO()
        ref = dict(image_bytes=512, hashtree=dict(image_bytes=512, fec_offset=512))
        stats = dict(requests=0, bytes=0, data_bytes=0, tree_bytes=0)
        with self.assertRaisesRegex(OSError, 'disconnected'):
            serve(console, io.BytesIO(bytes(512)), ref, float('inf'), stats, b'install', events)
        self.assertEqual(events.getvalue().splitlines(), [b'M1EVENT policy_write_entry fd=7 count=12',
                                                         b'M1EVENT policy_write_rc=-22 count=12'])
        self.assertEqual(console.writes[1], read_packet(io.BytesIO(bytes(512)), 512, 0, 512))
        self.assertEqual(stats['data_bytes'], 512)

    def test_vendor_replay_requires_switch_root_new_init_and_strict_policy(self):
        trial = json.loads((REFERENCE.parent/'gsi17-project-vendor-2026-11-11.json').read_text())['trials'][-1]
        log = '\n'.join(trial['observations'])
        ref = json.loads(REFERENCE.read_text())
        footer = next(line.split('=')[1] for line in trial['observations'] if line.startswith('last_block_sha256='))
        def check(text):
            return verify_first_stage(text, ref, footer, trial['vendor_image_sha256'], True)
        self.assertEqual(check(log)['stop'], 'policy-load-open')
        for before, after in [('254:1 / / ro', '254:2 / / ro'), ('7:0 / /vendor ro','7:1 / /vendor ro'),
                              ('flags=0x2000 rc=0','flags=0x2000 rc=-1'),
                              ('arg=selinux_setup','arg=second_stage'), ('strict_compile_rc=0','strict_compile_rc=1')]:
            with self.subTest(before=before), self.assertRaises(ValueError):
                check(log.replace(before, after))

    def test_first_stage_mount_matches_pid1_and_verity_device(self):
        evidence = json.loads((REFERENCE.parent/'gsi17-first-stage-2026-11-11.json').read_text())
        log = '\n'.join(evidence['observations'])
        ref = json.loads(REFERENCE.read_text())
        footer = next(row.split('=')[1] for row in evidence['observations'] if row.startswith('last_block_sha256='))
        observed = verify_first_stage(log, ref, footer)
        self.assertEqual(observed['boot_id'], evidence['boot_id'])
        self.assertIn('target=/dev ', observed['first_mount'])
        self.assertEqual(len(observed['partition_mounts']), 1)
        self.assertTrue(observed['partition_mounts'][0].endswith('rc=0'))
        with self.assertRaisesRegex(ValueError, 'PID 1'):
            verify_first_stage(log.replace('exec_pid=1 ', 'exec_pid=42 '), ref, footer)
        with self.assertRaisesRegex(ValueError, 'mountinfo'):
            verify_first_stage(log.replace('254:1 / /system', '254:0 / /system'), ref, footer)

    def test_transcript_matches_device_digest_across_usb_chunks(self):
        data = b'line with diagnostic output\n'*50

        class Console:
            def __init__(self, corrupt=False):
                self.corrupt = corrupt
                self.chunk = 0

            def write(self, cmd):
                if b'bs=384' in cmd:
                    if f'skip={self.chunk} '.encode() not in cmd:
                        raise AssertionError('unexpected chunk index')
                    start = self.chunk*384
                    block = data[start:start+384]
                    if self.corrupt and self.chunk == 1:
                        block = bytes(len(block))
                    payload = base64.encodebytes(block)
                    self.chunk += 1
                else:
                    payload = f'{len(data)} {hashlib.sha256(data).hexdigest()}'.encode()
                self.response = iter((b'MOUNT_BEGIN\n'+payload+b'\nMOUNT_END\n').splitlines(keepends=True))

            def read_until(self, delimiter):
                return next(self.response)

        self.assertEqual(transcript(Console()), data.decode())
        with self.assertRaisesRegex(ValueError, 'Incomplete USB transcript'):
            transcript(Console(corrupt=True))

    def test_direct_compiler_output_cannot_stand_in_for_init_child(self):
        child = '<6>init: Compiling SELinux policy\n<3>init: /system/bin/secilc: test error\n'
        log = ('init_selinux_setup_rc=134\n'+child+'secilc_rc=255\n'+child+
               'init_with_f20_mapping_rc=134\n'+child+'comparison_compiler_rc=255\n')
        self.assertEqual(init_policy_observations(log),
                         {'init_selinux_setup':134, 'init_with_f20_mapping':134})
        with self.assertRaisesRegex(ValueError, 'compiler child'):
            init_policy_observations(log.replace('<3>init: /system/bin/secilc: test error\n', '', 1))

    def test_random_read_including_final_sector(self):
        data = bytes(range(251))*16 + bytes(80)
        stream = io.BytesIO(data)
        for offset, count in ((3584,512), (0,4096), (1024,512)):
            response = read_packet(stream,len(data),offset,count)
            self.assertEqual(response[4:], data[offset:offset+count])
            self.assertEqual(struct.unpack('<I',response[:4])[0], zlib.crc32(response[4:]))

    def test_invalid_and_short_reads(self):
        stream = io.BytesIO(bytes(1024))
        for offset, count in ((0,0),(-512,512),(1024,512),(1,512),(0,8192),(0,1)):
            with self.assertRaises(ValueError):
                read_packet(stream,1024,offset,count)
        with self.assertRaises(IOError):
            read_packet(stream,4096,2048,1024)

    def test_image_hash_before_serving(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            verify_image(io.BytesIO(bytes(512)), {'image_bytes':512,'image_sha256':'0'*64})

    def test_mount_requires_the_pinned_root_and_device_files(self):
        ref = json.loads(REFERENCE.read_text())
        tree = ref['hashtree']
        sectors = tree['image_bytes']//512
        blocks = sectors//8
        footer = 'd'*64
        rows = [f"source_table=0 {ref['image_bytes']//512} user ",
                f"verity_table=0 {sectors} verity 1 254:0 254:0 4096 4096 {blocks} {blocks} sha256 {tree['root_digest']} {tree['salt']}",
                'mounted=/run/gsi17/mnt fs=ext4 options=ro,nosuid,nodev,noexec',
                f'verity_status=0 {sectors} verity V -', 'last_block_sha256='+footer,
                'ro.system.build.version.release=17', 'ro.system.build.version.sdk=37',
                'ro.system.build.id='+ref['build'], 'cleanup=0']
        rows += [f"file={name} sha256={item['sha256']}" for name,item in ref['files'].items()]
        log = '\n'.join(rows)
        verify_mount(log,ref,footer)
        with self.assertRaisesRegex(ValueError,'signed GSI descriptor'):
            verify_mount(log.replace(tree['root_digest'],'0'*64),ref,footer)
        with self.assertRaisesRegex(ValueError,'Missing mount result'):
            verify_mount('\n'.join(rows[:-1]),ref,footer)
