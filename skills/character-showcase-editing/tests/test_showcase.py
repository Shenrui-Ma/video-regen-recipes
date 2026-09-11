"""Pure data and mocked I/O tests. Never decode, render, or inspect media visually."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('showcase', Path(__file__).parents[1]/'scripts/showcase.py')
showcase = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(showcase)


def image(cid, **extra):
    return dict(id=cid, kind='image', path=f'assets/{cid}.png', **extra)


def video(cid, **extra):
    return dict(id=cid, kind='video', path=f'assets/{cid}.mp4', source_duration_seconds=10, **extra)


def manifest(mode='A'):
    result = {'schema_version': 1, 'mode': mode, 'output': 'output/new.mp4', 'audio': {'mode': 'silent'}}
    if mode in 'AB':
        result.update(total_frames=3900, clips=[image(str(i)) for i in range(11)])
    elif mode == 'C':
        result['clips'] = [image('i1', pair_id='p1', frames=272, scale_speed=4/3), video('v1', pair_id='p1', speed=1.1),
                           image('i2', pair_id='p2', frames=272), video('v2', pair_id='p2')]
    else:
        result['clips'] = [video('v1'), video('v2')]
    return result


class TimelineTests(unittest.TestCase):
    def plan(self, data):
        return showcase.make_plan(data, Path('/example-project'))

    def test_a_fixed_duration_and_delayed_background(self):
        plan = self.plan(manifest())
        self.assertEqual(plan['total_frames'], 3900)
        self.assertEqual(plan['boundaries_frames'], [round(i*3900/11) for i in range(12)])
        boundary = plan['boundaries_frames'][1]
        self.assertEqual(showcase.a_background(boundary+13, plan), 0)
        self.assertEqual(showcase.a_background(boundary+14, plan), 1)
        layers = showcase.a_layers(boundary, plan)
        self.assertAlmostEqual(layers[1][2], 12/25)
        self.assertEqual(layers[1][1], 0)

    def test_b_expands_inputs_instead_of_shortening_output(self):
        plan = self.plan(manifest('B'))
        self.assertEqual(sum(c['frames'] for c in plan['clips']), 3900+10*25)
        self.assertEqual(plan['total_frames'], 3900)
        last = plan['clips'][-1]
        self.assertEqual(last['start_frame']+last['frames'], 3900)
        self.assertEqual(plan['intro_frames'], 50)
        self.assertEqual(plan['end_fade_frames'], 0)

    def test_c_overlap_and_corresponding_pairs(self):
        plan = self.plan(manifest('C'))
        lengths = [272, round(10/1.1*60), 272, 600]
        self.assertEqual([c['frames'] for c in plan['clips']], lengths)
        self.assertEqual(plan['total_frames'], sum(lengths)-90)
        self.assertEqual(plan['transition_offsets_frames'], [272-30, 272+lengths[1]-60, 272+lengths[1]+272-90])
        bad = manifest('C')
        bad['clips'][1]['pair_id'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'pair_id'):
            self.plan(bad)

    def test_d_hard_cuts_remove_no_frames(self):
        data = manifest('D')
        data['transition_frames'] = 0
        plan = self.plan(data)
        self.assertEqual(plan['total_frames'], 1200)
        self.assertEqual(plan['layout']['mode'], 'plain')
        command = showcase.compose_command(plan, ['part1.mp4', 'part2.mp4'], 'out.mp4')
        fc = command[command.index('-filter_complex')+1]
        self.assertIn('concat=n=2:v=1:a=0', fc)
        self.assertNotIn('xfade=', fc)

    def test_swimsuit_duration_frame_quantization(self):
        windows = [(10.116667, 3, 4, 1), (15.083333, 6, 9.083333, 1.4), (10.116667, 0, 10.116667, 1.2),
                   (15.083333, 0, 15.083333, 1), (10.116667, 0, 10.116667, 1.2), (10.116667, 0, 5, 1),
                   (10.116667, 0, 6, 1), (10.116667, 0, 10.116667, 1)]
        data = manifest('D')
        data['transition_frames'] = 12
        data['clips'] = [dict(id=str(i), kind='video', path=f'{i}.mp4', source_duration_seconds=d,
                              source_start_seconds=start, source_take_seconds=take, speed=speed)
                         for i, (d, start, take, speed) in enumerate(windows)]
        self.assertEqual(self.plan(data)['total_frames'], 3729)

    def test_curve_endpoints_and_original_tangents(self):
        for frame, expected, _, _ in showcase.SCALE_KFS:
            self.assertAlmostEqual(showcase.scale_at(frame), expected)
        self.assertAlmostEqual(showcase.scale_at(61.5), 269.70955028224415)
        self.assertEqual(showcase.scale_at(9999), 104)
        self.assertEqual(showcase.scale_at(310.733/(4/3), speed=4/3), 104)
        self.assertAlmostEqual(showcase.scale_at(123, fps=30), showcase.scale_at(246))
        self.assertEqual(showcase.blur_at(91.117), 0)
        self.assertGreater(showcase.blur_at(70), 0)

    def test_fit_and_cover_preserve_ratio(self):
        self.assertEqual(showcase.fitted_size(1600, 900, 1080, 1080), (1080, 608))
        self.assertEqual(showcase.fitted_size(1600, 900, 1080, 1080, 'cover'), (1920, 1080))
        self.assertEqual(showcase.fitted_size(1000, 1000, 1080, 1080, scale=1.04), (1123, 1123))

    def test_c_requires_matching_image_video_endpoint_geometry(self):
        plan = self.plan(manifest('C'))
        image_end = showcase.scale_at(9999)/100
        self.assertEqual(image_end, 1.04)
        foreground_box = round(plan['canvas']['width']*image_end)
        self.assertIn(f'scale={foreground_box}:{foreground_box}', showcase.video_filter(plan['clips'][1], plan))
        for mode in ('plain', 'blurred-fill'):
            bad = manifest('C')
            bad['layout'] = {'mode': mode}
            with self.assertRaisesRegex(ValueError, 'same 104%'):
                self.plan(bad)

    def test_bad_settings_are_not_silently_ignored(self):
        cases = []
        bad = manifest(); bad['mystery'] = 1; cases.append(bad)
        bad = manifest(); bad['canvas'] = {'width': 1079}; cases.append(bad)
        bad = manifest(); bad['canvas'] = {'fps': float('nan')}; cases.append(bad)
        bad = manifest(); bad['total_frames'] = True; cases.append(bad)
        bad = manifest(); bad['transition_frames'] = 30; cases.append(bad)
        bad = manifest('D'); bad['total_frames'] = 1200; cases.append(bad)
        bad = manifest('D'); bad['clips'][0]['scale_speed'] = 1.2; cases.append(bad)
        bad = manifest('D'); bad['clips'][0]['source_start_seconds'] = 9; bad['clips'][0]['source_take_seconds'] = 2; cases.append(bad)
        bad = manifest('D'); bad['clips'][0]['speed'] = 0; cases.append(bad)
        bad = manifest('D'); bad['audio'] = {'mode': 'natural'}; cases.append(bad)
        bad = manifest('D'); bad['audio'] = {'mode': 'silent', 'path': 'music.mp3'}; cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.plan(bad)

    def test_no_triple_transition_overlap(self):
        data = manifest('D')
        data['clips'].append(video('v3', source_take_seconds=.9))
        data['clips'][1]['source_take_seconds'] = .9
        with self.assertRaisesRegex(ValueError, 'too short'):
            self.plan(data)

    def test_check_only_requires_files_without_decoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = manifest('D')
            with self.assertRaisesRegex(ValueError, 'missing input'):
                showcase.make_plan(data, root, require_files=True)
            (root/'assets').mkdir()
            for clip in data['clips']:
                (root/clip['path']).write_bytes(b'not a real video; file check does not decode')
            with patch.object(showcase, 'probe', side_effect=AssertionError('must not probe')), patch.object(showcase.subprocess, 'run', side_effect=AssertionError('must not run')):
                showcase.make_plan(data, root, require_files=True)
            (root/'output').mkdir()
            (root/'output/new.mp4').write_bytes(b'existing')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                showcase.make_plan(data, root)

    def test_bgm_source_seek_and_output_delay_are_independent(self):
        data = manifest('D')
        data['audio'] = {'mode': 'bgm', 'path': 'music.m4a', 'source_start_seconds': 1, 'output_start_seconds': 2}
        plan = self.plan(data)
        command = showcase.compose_command(plan, ['p0.mp4', 'p1.mp4'], 'out.mp4')
        fc = command[command.index('-filter_complex')+1]
        self.assertIn('atrim=start=1.0:duration=17.500000000000', fc)
        self.assertIn('adelay=96000S:all=1', fc)
        self.assertIn('-stream_loop', command)

    def test_source_audio_speed_silence_and_mixing(self):
        data = manifest('C')
        data['audio'] = {'mode': 'source+bgm', 'path': 'music.m4a', 'gain_db': -12}
        plan = self.plan(data)
        for clip in plan['clips']:
            clip['has_audio'] = clip['id'] == 'v1'
        command = showcase.compose_command(plan, ['p0.mp4', 'p1.mp4', 'p2.mp4', 'p3.mp4'], 'out.mp4')
        fc = command[command.index('-filter_complex')+1]
        self.assertIn('[4:a:0]atrim=', fc)
        self.assertIn('[5:a:0]aresample', fc)
        self.assertIn('atempo=1.100000000000', fc)
        self.assertEqual(fc.count('anullsrc='), 3)
        self.assertEqual(fc.count('acrossfade='), 3)
        self.assertIn('volume=-12.0dB', fc)
        self.assertIn('normalize=0', fc)

    def test_atempo_is_decomposed_for_extreme_speeds(self):
        for speed in (.1, .25, 1, 1.4, 4, 10):
            values = [float(term.split('=')[1]) for term in showcase.atempo_chain(speed).split(',')]
            self.assertTrue(all(.5 <= x <= 2 for x in values))
            self.assertAlmostEqual(math.prod(values), speed)

    def test_video_has_no_still_keyframes_and_intro_blur_is_once(self):
        data = manifest('D')
        data.update(intro_blur_frames=30, layout={'mode': 'blurred-fill', 'fit': 'contain'})
        plan = self.plan(data)
        vf = showcase.video_filter(plan['clips'][0], plan)
        self.assertNotIn('312', vf)
        self.assertIn('force_original_aspect_ratio=decrease', vf)
        fc = showcase.compose_command(plan, ['p0.mp4', 'p1.mp4'], 'out.mp4')
        self.assertEqual(fc[fc.index('-filter_complex')+1].count('blend=all_expr'), 1)

    def test_render_failure_has_no_success_report(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = showcase.make_plan(manifest('D'), Path(directory))
            with patch.object(showcase.shutil, 'which', return_value='/fake/bin'), patch.object(showcase, 'preflight_media'), patch.object(showcase, 'render_images', side_effect=RuntimeError('deliberate failure')):
                with self.assertRaisesRegex(RuntimeError, 'deliberate failure'):
                    showcase.render(plan)
            self.assertFalse(Path(plan['output']).exists())
            self.assertFalse(Path(plan['report']).exists())
            self.assertFalse(Path(plan['output']).with_suffix('.render.lock').exists())

    def test_preflight_records_absent_audio_and_rejects_duration_mismatch(self):
        plan = self.plan(manifest('D'))
        response = {'streams': [{'index': 0, 'codec_type': 'video', 'duration': '10', 'sample_aspect_ratio': '1:1'}]}
        with patch.object(showcase, 'probe', return_value=response):
            showcase.preflight_media(plan)
        self.assertFalse(plan['clips'][0]['has_audio'])
        response['streams'][0]['duration'] = '9'
        with patch.object(showcase, 'probe', return_value=response), self.assertRaisesRegex(ValueError, 'declared source duration'):
            showcase.preflight_media(plan)

    def test_attached_cover_does_not_replace_real_video_stream(self):
        plan = self.plan(manifest('D'))
        response = {'streams': [
            {'index': 0, 'codec_type': 'video', 'duration': '0', 'disposition': {'attached_pic': 1}},
            {'index': 1, 'codec_type': 'video', 'duration': '10', 'sample_aspect_ratio': '1:1'},
            {'index': 2, 'codec_type': 'audio', 'duration': '10'}]}
        with patch.object(showcase, 'probe', return_value=response):
            showcase.preflight_media(plan)
        self.assertTrue(plan['clips'][0]['has_audio'])
        self.assertEqual(plan['clips'][0]['video_stream_index'], 1)
        self.assertTrue(showcase.video_filter(plan['clips'][0], plan).startswith('[0:1]trim='))

    def test_preflight_rejects_short_nonloop_music(self):
        data = manifest('B')
        data['audio'] = {'mode': 'bgm', 'path': 'music.m4a', 'loop': False}
        plan = self.plan(data)
        with patch.object(showcase, 'probe', return_value={'streams': [{'codec_type': 'audio', 'duration': '10'}]}), self.assertRaisesRegex(ValueError, 'too short'):
            showcase.preflight_media(plan)

    def test_source_audio_hard_cuts_use_audio_concat(self):
        data = manifest('D')
        data.update(transition_frames=0, audio={'mode': 'source'})
        plan = self.plan(data)
        for clip in plan['clips']:
            clip['has_audio'] = False
        command = showcase.compose_command(plan, ['p0.mp4', 'p1.mp4'], 'out.mp4')
        fc = command[command.index('-filter_complex')+1]
        self.assertIn('concat=n=2:v=0:a=1', fc)
        self.assertNotIn('acrossfade=', fc)

    def test_final_validation_failure_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = showcase.make_plan(manifest('D'), Path(directory))
            def fake_run(command):
                Path(command[-1]).write_text('fake bytes, never a real video')
            with patch.object(showcase.shutil, 'which', return_value='/fake/bin'), patch.object(showcase, 'preflight_media'), patch.object(showcase, 'render_images', return_value=['unused.mp4']), patch.object(showcase, 'run', side_effect=fake_run), patch.object(showcase, 'probe', return_value={'streams': [{'codec_type': 'video', 'nb_frames': '1'}]}):
                with self.assertRaisesRegex(ValueError, 'frame count'):
                    showcase.render(plan)
            self.assertFalse(Path(plan['output']).exists())
            self.assertFalse(Path(plan['report']).exists())


if __name__ == '__main__':
    unittest.main()
