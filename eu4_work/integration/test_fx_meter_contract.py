from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SHARED = (ROOT / "eu4_work/integration/fx_shared.h").read_text()
AUDIO = (ROOT / "eu4_work/integration/fx_audio.cpp").read_text()
UI = (ROOT / "eu4_work/integration/fx_ui.c").read_text()


class FxMeterContractTests(unittest.TestCase):
    def test_request_uses_existing_mailbox_padding(self):
        self.assertIn("int values[8][18];u32 meter_track;", SHARED)
        self.assertIn("MailMeterTrackOffset[(__builtin_offsetof(FxMail,meter_track)==0x268)", SHARED)
        self.assertIn("sizeof(FxMail)<=0x280", SHARED)
        self.assertIn("FX_METER_TRACKS TRACKS", SHARED)
        self.assertIn("MAIL->meter_track=meter_track", UI)
        self.assertIn("publish_request(page==0x1a?U->selected:FX_METER_TRACKS)", UI)
        self.assertIn("meter_track>FX_METER_TRACKS", AUDIO)
        self.assertIn("track==A->requested_track", AUDIO)
        self.assertIn("FX_METER_TAG(serial,track)", SHARED)
        self.assertIn("FX_METER_TAG(U->serial,U->selected)", UI)

    def test_publication_fits_before_motion_owned_line(self):
        self.assertIn("FX_METER_REQUEST_OFFSET 0x2b0u", SHARED)
        self.assertIn("FX_METER_PUB_OFFSET 0x2b4u", SHARED)
        self.assertIn("sizeof(Meta)==0x2c0", AUDIO)
        self.assertIn("requested_track)==FX_METER_REQUEST_OFFSET", AUDIO)
        self.assertIn("meter)==FX_METER_PUB_OFFSET", AUDIO)
        self.assertIn("clean(FX_METER_CACHE_LINE,FX_METER_CACHE_LINE+32)", AUDIO)
        self.assertEqual(0x240416C0 + 0x2C0, 0x24041980)

    def test_mail_invalidation_stays_inside_its_owned_reservation(self):
        self.assertIn("((sizeof(FxMail)+31u)&~31u)", AUDIO)
        self.assertEqual((0x268 + 4 + 31) & ~31, 0x280)

    def test_audio_publishes_only_real_selected_track_readings(self):
        self.assertIn("tf_meters((void*)DSP_ADDR,track,&meters)", AUDIO)
        self.assertIn("track==A->requested_track", AUDIO)
        self.assertIn("publish_meter(track,reduction)", AUDIO)
        self.assertIn("m->request_tag=FX_METER_TAG(A->serial,track)", AUDIO)
        self.assertRegex(AUDIO, r"meters\.reduction_db==meters\.reduction_db")
        self.assertRegex(AUDIO, r"meters\.reduction_db>=0")
        body = AUDIO.split("static void publish_meter", 1)[1].split(
            "static int memory", 1
        )[0]
        self.assertEqual(body.count("clean(FX_METER_CACHE_LINE"), 2)
        self.assertLess(body.index("m->serial=serial|1u"),
                        body.index("m->request_tag="))
        self.assertLess(body.index("m->serial=serial;"),
                        body.rindex("clean(FX_METER_CACHE_LINE"))
        self.assertIn("publish_meter(FX_METER_TRACKS,0)", AUDIO)

    def test_ui_read_is_bounded_coherent_and_selection_checked(self):
        self.assertIn("fx_screen_meter_snapshot(float *reduction_db)", UI)
        self.assertIn("for(u32 attempt=0;attempt<2;attempt++)", UI)
        self.assertIn("if(before!=m->serial)continue", UI)
        self.assertIn("FX_METER_TAG(U->serial,U->selected)", UI)
        reader = UI.split("int fx_screen_meter_snapshot", 1)[1].split(
            "int fx_screen_hit", 1
        )[0]
        self.assertIn("union {float value;u32 bits;} reduction", reader)
        self.assertNotRegex(reader, r"\b(?:db|reduction\.value)\s*(?:<|>|==|!=)")
        self.assertIn("return 0;", UI)


if __name__ == "__main__":
    unittest.main()
