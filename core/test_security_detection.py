import unittest
from core.security_detection import PersonConfirmation, person_candidate


def person(x=.2, score=.85):
    return dict(label='pessoa', score=score, box=[x, .2, .1, .4])


class PersonDetectionTests(unittest.TestCase):
    def test_rejects_ambiguous_tiny_and_padding_detections(self):
        self.assertFalse(person_candidate(.8, .75, (20, 20, 80, 200), 960, 540))
        self.assertFalse(person_candidate(.9, .1, (20, 20, 3, 10), 960, 540))
        self.assertFalse(person_candidate(.9, .1, (20, 600, 80, 200), 960, 540))
        self.assertTrue(person_candidate(.9, .1, (20, 20, 80, 200), 960, 540))

    def test_requires_three_consistent_observations_and_keeps_moving_person(self):
        gate = PersonConfirmation()
        self.assertEqual(gate.filter('one', [person()], 0), [])
        self.assertEqual(gate.filter('one', [person(.24)], 1.5), [])
        self.assertEqual(gate.filter('one', [person(.28)], 3), [person(.28)])

    def test_flicker_different_locations_low_scores_and_gaps_do_not_confirm(self):
        gate = PersonConfirmation()
        gate.filter('one', [person()], 0)
        gate.filter('one', [], 1.5)
        self.assertEqual(gate.filter('one', [person()], 3), [])
        self.assertEqual(gate.filter('one', [person(.8)], 4.5), [])
        self.assertEqual(gate.filter('one', [person(.8, score=.6)], 6), [])
        self.assertEqual(gate.filter('one', [person(.8)], 20), [])

    def test_separate_cameras_and_reconnections_do_not_share_confirmation(self):
        gate = PersonConfirmation()
        gate.filter('one', [person()], 0)
        gate.filter('one', [person()], 1)
        self.assertEqual(gate.filter('two', [person()], 2), [])
        gate.reset('one')
        self.assertEqual(gate.filter('one', [person()], 2), [])

    def test_vehicles_pass_through_and_one_track_cannot_confirm_two_people(self):
        gate = PersonConfirmation()
        car = dict(label='carro', score=.6)
        self.assertEqual(gate.filter('one', [car], 0), [car])
        gate.filter('one', [person()], 1)
        gate.filter('one', [person()], 2)
        result = gate.filter('one', [person(), person(.21)], 3)
        self.assertEqual(len(result), 1)


if __name__ == '__main__': unittest.main()
