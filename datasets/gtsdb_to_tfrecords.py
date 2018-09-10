
"""Converts Pascal VOC data to TFRecords file format with Example protos.

The raw Pascal VOC data set is expected to reside in JPEG files located in the
directory 'JPEGImages'. Similarly, bounding box annotations are supposed to be
stored in the 'Annotation directory'

This TensorFlow script converts the training and evaluation data into
a sharded data set consisting of 1024 and 128 TFRecord files, respectively.

Each validation TFRecord file contains ~500 records. Each training TFREcord
file contains ~1000 records. Each record within the TFRecord file is a
serialized Example proto. The Example proto contains the following fields:

    image/encoded: string containing JPEG encoded image in RGB colorspace
    image/height: integer, image height in pixels
    image/width: integer, image width in pixels
    image/channels: integer, specifying the number of channels, always 3
    image/format: string, specifying the format, always'JPEG'


    image/object/bbox/xmin: list of float specifying the 0+ human annotated
        bounding boxes
    image/object/bbox/xmax: list of float specifying the 0+ human annotated
        bounding boxes
    image/object/bbox/ymin: list of float specifying the 0+ human annotated
        bounding boxes
    image/object/bbox/ymax: list of float specifying the 0+ human annotated
        bounding boxes
    image/object/bbox/label: list of integer specifying the classification index.
    image/object/bbox/label_text: list of string descriptions.

Note that the length of xmin is identical to the length of xmax, ymin and ymax
for each example.
"""
import os
import sys
import random
import re
import numpy as np
import tensorflow as tf

import xml.etree.ElementTree as ET

from dataset_utils import int64_feature, float_feature, bytes_feature
#from datasets.pascalvoc_datasets import VOC_LABELS
import math

DIRECTORY_ANNOTATIONS = ''
DIRECTORY_IMAGES = ''


def _process_image(directory, name):
    """Process a image and annotation file.

    Args:
      filename: string, path to an image file e.g., '/path/to/example.JPG'.
      coder: instance of ImageCoder to provide TensorFlow image coding utils.
    Returns:
      image_buffer: string, JPEG encoding of RGB image.
      height: integer, image height in pixels.
      width: integer, image width in pixels.
    """
    # Read the image file.
    filename = directory + name + '.jpg'
    image_data = tf.gfile.FastGFile(filename, 'rb').read()
    gt = open("gt.txt", "r")
    # Read the ground truth annotation file.
    #filename = os.path.join(directory, DIRECTORY_ANNOTATIONS, name + '.txt')
    #tree = ET.parse(filename)
    #root = tree.getroot()s

    # Image shape.
    #size = root.find('size')
    shape = [int(800),
		     int(1360),
		     int(3)]
    # Find annotations.
    bboxes = []
    labels = []
    labels_text = []
    difficult = []
    truncated = []
    for line in gt:
        if re.match(name + "(.*)", line):
            obj=re.findall(r'\d+',line)
    #for obj in root.findall('object'):
        #label = obj.find('name').text
            labels.append(int(obj[5]))#int(VOC_LABELS[label][0]))
        #if(int(VOC_LABELS[label][0]) == 0):
        #    print(filename)
        #    raise 
        
            labels_text.append(obj[5].encode('ascii'))          
            difficult.append(0)
            truncated.append(0)
            #bboxes.append((float(bbox.find('ymin').text) / shape[0],
            #               float(bbox.find('xmin').text) / shape[1],
            #               float(bbox.find('ymax').text) / shape[0],
            #               float(bbox.find('xmax').text) / shape[1]
            #               )) 
            bboxes.append((float(obj[2]) / shape[0],
                           float(obj[1]) / shape[1],
                           float(obj[4]) / shape[0],
                           float(obj[3]) / shape[1]
                           ))
            if (float(obj[1]) <= 1 or float(obj[2]) <= 1 or float(obj[3]) >= shape[1]-1 or float(obj[4]) >=shape[0]-1):
                print('out of bound ' + line)
            if (float(obj[3]) - float(obj[1]) < 20 or float(obj[4]) - float(obj[2]) < 20):
                print('too small ' + line)
               	if(os.path.isfile(filename)):
                    os.remove(filename)
            if (float(obj[3]) < float(obj[1])  or float(obj[4]) < float(obj[2]) ):
                print('wrong annotations ' + line)
    print(shape)
    print(bboxes)
    print(labels)
    print(labels_text)
    print(difficult)
    print(truncated)
    return image_data, shape, bboxes, labels, labels_text, difficult, truncated


def _convert_to_example(image_data, labels, labels_text, bboxes, shape,
                        difficult, truncated,name):
    """Build an Example proto for an image example.

    Args:
      image_data: string, JPEG encoding of RGB image;
      labels: list of integers, identifier for the ground truth;
      labels_text: list of strings, human-readable labels;
      bboxes: list of bounding boxes; each box is a list of integers;
          specifying [xmin, ymin, xmax, ymax]. All boxes are assumed to belong
          to the same label as the image label.
      shape: 3 integers, image shapes in pixels.
    Returns:
      Example proto
    """
    xmin = []
    ymin = []
    xmax = []
    ymax = []
    for b in bboxes:
        assert len(b) == 4
        # pylint: disable=expression-not-assigned
        [l.append(point) for l, point in zip([ymin, xmin, ymax, xmax], b)]
        # pylint: enable=expression-not-assigned

    image_format = b'JPEG'
    example = tf.train.Example(features=tf.train.Features(feature={
            'image/height': int64_feature(shape[0]),
            'image/width': int64_feature(shape[1]),
            'image/channels': int64_feature(shape[2]),
            'image/shape': int64_feature(shape),
            'image/object/bbox/xmin': float_feature(xmin),
            'image/object/bbox/xmax': float_feature(xmax),
            'image/object/bbox/ymin': float_feature(ymin),
            'image/object/bbox/ymax': float_feature(ymax),
            'image/object/bbox/label': int64_feature(labels),
            'image/object/bbox/label_text': bytes_feature(labels_text),
            'image/object/bbox/difficult': int64_feature(difficult),
            'image/object/bbox/truncated': int64_feature(truncated),
            'image/format': bytes_feature(image_format),
            'image/filename': bytes_feature(name.encode('utf-8')),
            'image/encoded': bytes_feature(image_data)}))
    return example


def _add_to_tfrecord(dataset_dir, name, tfrecord_writer):
    """Loads data from image and annotations files and add them to a TFRecord.

    Args:
      dataset_dir: Dataset directory;
      name: Image name to add to the TFRecord;
      tfrecord_writer: The TFRecord writer to use for writing.
    """
    image_data, shape, bboxes, labels, labels_text, difficult, truncated = \
        _process_image(dataset_dir, name)
    example = _convert_to_example(image_data, labels, labels_text,
                                  bboxes, shape, difficult, truncated,name)
    tfrecord_writer.write(example.SerializeToString())


def _get_output_filename(output_dir, name):
    return '%s/%s.tfrecord' % (output_dir, name)

def _get_dataset_filename(dataset_dir, name, shard_id, num_shard, records_num):
    output_filename = '%s_%05d-of-%05d-total%05d.tfrecord' % (name, shard_id + 1, num_shard,records_num)
    return os.path.join(dataset_dir, output_filename)

def run(dataset_dir, output_dir, name, shuffling=False):
    """Runs the conversion operation.

    Args:
      dataset_dir: The dataset directory where the dataset is stored.
      output_dir: Output directory.
    """
    

    # Dataset filenames, and shuffling.
    path = os.path.join(dataset_dir, DIRECTORY_ANNOTATIONS)
    if not tf.gfile.Exists(path):
        raise Exception("{} does not exist".format(path))
    
    filenames = sorted(os.listdir(path))
    if shuffling:
        random.seed(12345)
        random.shuffle(filenames)

    # Process dataset files.
    num_per_shard = 2000
    num_shard = int(math.ceil(len(filenames) / float(num_per_shard)))
    
    for shard_id in range(num_shard):
        start_ndx = shard_id * num_per_shard
        end_ndx = min((shard_id+1) * num_per_shard, len(filenames))
        records_num = end_ndx - start_ndx
        tf_filename = _get_dataset_filename(output_dir, name, shard_id, num_shard, records_num)
        with tf.python_io.TFRecordWriter(tf_filename) as tfrecord_writer:
            for i in range(start_ndx, end_ndx):
                filename = filenames[i]
                
                print('Converting image %d/%d %s shard %d' % (i+1, len(filenames), filename[:-4], shard_id+1))
                #save the file to tfrecords
                _add_to_tfrecord(dataset_dir, filename[:-4], tfrecord_writer)

    # Finally, write the labels file:
    # labels_to_class_names = dict(zip(range(len(_CLASS_NAMES)), _CLASS_NAMES))
    # dataset_utils.write_label_file(labels_to_class_names, dataset_dir)
    print('\nFinished converting the Pascal VOC dataset!')
    
    
if __name__ == "__main__": 
#     dataset_dir = "../../data/voc/2007_train/VOCdevkit/VOC2007/"
#     output_dir = "../../data/voc/tfrecords/"
#     name='voc_train_2007'
 
#     dataset_dir = "../../data/voc/2012_train/VOCdevkit/VOC2012/"
#     output_dir = "../../data/voc/tfrecords/"
#     name='voc_train_2012'
    
#    dataset_dir = "train/"
#    output_dir = "tfrecords/"
#    name='gtsdb_train'

    dataset_dir = "test/"
    output_dir = "tfrecords/"
    name='gtsdb_test'
    
    run(dataset_dir, output_dir, name=name, shuffling=False)
    
    
    
    
    