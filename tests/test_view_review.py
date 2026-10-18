"""Approval safety rules need no commercial software, licence or model weights."""
import copy
from types import SimpleNamespace
import unittest
from shapecast_linux.view_review import KEY, ReviewConflict, review_state, checked_state, accept_view, approved_keys, save_state, ReviewManager


class ReviewRulesTests(unittest.TestCase):
    def setUp(self):
        self.state = {'schema':1,'phase':'pending','revision':4,'front_key':'job/front.png','error':None,'active':None,
                      'views':{name:{'key':'job/'+name+'.png','accepted':False,'generation':0} for name in ('left','back','right')}}
        self.job = SimpleNamespace(id='job-id',prompt_raw='test creature',status='awaiting_selection',params={KEY:copy.deepcopy(self.state)})

    def test_review_state_is_a_copy_not_an_untracked_json_mutation(self):
        state = review_state(self.job);accept_view(state,'left')
        self.assertFalse(self.job.params[KEY]['views']['left']['accepted'])
        save_state(self.job,state)
        self.assertTrue(self.job.params[KEY]['views']['left']['accepted'])

    def test_only_the_approved_view_changes(self):
        before=copy.deepcopy(self.state);accept_view(self.state,'left')
        self.assertEqual(self.state['revision'],5)
        for name in ('back','right'):self.assertEqual(self.state['views'][name],before['views'][name])
        self.assertEqual(self.state['front_key'],before['front_key'])

    def test_cannot_continue_until_every_view_is_approved(self):
        for name in ('left','back'):
            accept_view(self.state,name)
            with self.assertRaises(ReviewConflict):approved_keys(self.state)
        accept_view(self.state,'right')
        self.assertEqual(approved_keys(self.state),{n:'job/'+n+'.png' for n in ('left','back','right')})

    def test_stale_or_invalid_revisions_cannot_approve(self):
        for revision in (3,5,True,'4',None):
            with self.subTest(revision=revision),self.assertRaises(ReviewConflict):checked_state(self.job,revision)
        self.assertEqual(checked_state(self.job,4),self.state)

    def test_busy_cancelled_and_completed_jobs_cannot_approve(self):
        for status in ('generating_image','generating_shape','cancelled','complete','failed'):
            self.job.status=status
            with self.subTest(status=status),self.assertRaises(ReviewConflict):checked_state(self.job,4)
        self.job.status='awaiting_selection';self.job.params[KEY]['phase']='regenerating'
        with self.assertRaises(ReviewConflict):checked_state(self.job,4)

    def test_invalid_view_cannot_be_approved(self):
        for name in ('front','../private','unknown',None):
            with self.subTest(name=name),self.assertRaises(ReviewConflict):accept_view(self.state,name)

    def test_completed_and_cancelled_reviews_are_not_shown(self):
        manager=ReviewManager(SimpleNamespace())
        self.assertEqual(manager.snapshot(self.job)['revision'],4)
        for status in ('cancelled','complete','generating_shape'):
            self.job.status=status;self.assertIsNone(manager.snapshot(self.job))

    def test_approved_replacement_key_is_passed_through_exactly(self):
        self.state['views']['back']['key']='job/review/new/back.png'
        for name in self.state['views']:accept_view(self.state,name)
        self.assertEqual(approved_keys(self.state)['back'],'job/review/new/back.png')

if __name__=='__main__':unittest.main()
