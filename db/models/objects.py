import os
import re
import json
from collections import OrderedDict

from scipy.io import loadmat, savemat

from ...lib.array_utils import GrowingLILMatrix


FEATURE_DIRECTORY = 'histograms'
FEATURES = ['SURF', 'color', 'SURF_pairs', 'color_pairs', 'color_triplets']
FEATURES_INDEX = {'SURF': 0, 'color': 1, 'SURF_pairs': 2, 'color_pairs': 3,
                  'color_triplets': 4}


def _string_to_object_view(s):
    return tuple([int(i) for i in s.split()])


def _string_to_features(s):
    return [float(i) for i in s.split()]


class WrongNumberOfFeatures(Exception):
    pass


class Frame(object):

    def __init__(self, filename, label, timestamp, object_views):
        # objects = ([label, ]view id, obj id, position_x, position_y)
        if len(object_views) == 4:
            object_views = (None, object_views[0], object_views[1],
                            object_views[2], object_views[3])
        self.label = label  # Ground truth lables for objects in scene
        self.timestamp = timestamp
        self.views = object_views  # Recognized views of objects
        self.filename = filename

    def get_full_path(self, path):
        return os.path.join(path, FEATURE_DIRECTORY, self.filename)

    def read_features(self, path):
        with open(self.get_full_path(path), 'r') as f:
            # also remove empty lines
            lines = [l for l in f.readlines()[::-1] if not l.isspace()]
            lines.reverse()
            if len(lines) != len(self.views) * len(FEATURES):
                raise WrongNumberOfFeatures()
            return [[_string_to_features(lines.pop()) for f in FEATURES]
                    for o in self.views]

    def to_dict(self):
        return {'views': self.views,
                'label': self.label,
                'timestamp': self.timestamp,
                'filename': self.filename,
                'object-views': self.views}

    @classmethod
    def from_line(cls, line):
        blocks = line.split('|')
        filename = blocks[0][:-1]
        views = [_string_to_object_view(s) for s in blocks[1:]]
        label, timestamp = Frame._parse_filename_name(filename)
        return Frame(filename, label, timestamp, views)

    @classmethod
    def from_dict(cls, d):
        return Frame(d['filename'], d['label'],
                     d['timestamp'], d['object-views'])

    @classmethod
    def _parse_filename_name(cls, name):
        m = re.search(r"_o(?P<label>[0-9]+)_(?P<time>[0-9]+.[0-9]+)$", name)
        if m:
            return (int(m.group('label')), float(m.group('time')))
        else:
            raise ValueError("Could not extract label and time from name (%s)"
                             % name)


class ObjectDB(object):

    def __init__(self, object_names=None):
        self.frames = []
        self.histos = [GrowingLILMatrix() for dummy in FEATURES]
        self.object_names = object_names

    def add_frame(self, frame):
        self.frames.append(frame)

    def add_feats(self, feats):
        for feat, histo in zip(feats, self.histos):
            histo.add_row(feat)

    def save(self, path, name):
        meta_file = os.path.join(path, name + '.json')
        data_file = os.path.join(path, name + '.mat')
        d = OrderedDict()
        if self.object_names is not None:
            d['object_names'] = self.object_names
        d['data_file'] = name + '.mat'
        d['frames'] = [frame.to_dict() for frame in self.frames]
        with open(meta_file, 'w') as f:
            json.dump(d, f, indent=2)
        savemat(data_file, dict(zip(FEATURES, self.histos)))

    def get_histo_matrix(self, histo_type):
        return self.histos[FEATURES_INDEX[histo_type]]

    @classmethod
    def build_from(cls, path, object_names=None, verbosity='quiet'):
        """Collect stat and feature files.
        :arg path: string
            path to statistics file, containing feature file names
        """
        db = ObjectDB(object_names=object_names)
        # Parse stat file
        with open(path, 'r') as f:
            frames = [Frame.from_line(l) for l in f.readlines()
                      if not l.isspace()]
        # Parse all frames
        skipped = 0
        for f in frames:
            try:
                for obj_feat in f.read_features(os.path.dirname(path)):
                    db.add_feats(obj_feat)
                db.add_frame(f)
            except IOError, e:
                skipped += 1
                if verbosity is 'verbose':
                    print "Skipping file %s (%s)" % (f.filename, e.strerror)
            except WrongNumberOfFeatures:
                skipped += 1
                if verbosity is 'verbose':
                    print("Skipping file %s (wrong number of features)"
                          % f.filename)
        if skipped > 0 and verbosity is not 'silent':
            print "Skipped %d files." % skipped
        return db

    @classmethod
    def load(cls, path):
        with open(path, 'r') as f:
            meta = json.load(f)
            object_names = meta.get('object_names', None)
            db = ObjectDB(object_names=object_names)
            for f in meta['frames']:
                db.add_frame(Frame.from_dict(f))
            if 'data_file' in meta:
                data = loadmat(os.path.join(os.path.dirname(path),
                                            meta['data_file']))
                db.histos = [data[feat] for feat in FEATURES]
            return db
