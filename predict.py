#! /usr/bin/env python

import os
import argparse
import json
import cv2
from utils.utils import get_yolo_boxes, makedirs
from utils.bbox import draw_boxes, draw_box
from keras.models import load_model
from tqdm import tqdm
import numpy as np
try:
    from PIL import Image
except ImportError:
    import Image
import pytesseract
import sys

def _main_(args):
    config_path  = args.conf
    input_path   = args.input
    output_path  = args.output

    with open(config_path) as config_buffer:    
        config = json.load(config_buffer)

    makedirs(output_path)

    ###############################
    #   Set some parameter
    ###############################       
    net_h, net_w = 416, 416 # a multiple of 32, the smaller the faster
    obj_thresh, nms_thresh = 0.5, 0.45

    ###############################
    #   Load the model
    ###############################
    os.environ['CUDA_VISIBLE_DEVICES'] = config['train']['gpus']
    infer_model = load_model(config['train']['saved_weights_name'])

    ###############################
    #   Predict bounding boxes 
    ###############################
    if 'webcam' in input_path: # do detection on the first webcam
        video_reader = cv2.VideoCapture(0)

        # the main loop
        batch_size  = 1
        images      = []
        while True:
            ret_val, image = video_reader.read()
            if ret_val == True: images += [image]

            if (len(images)==batch_size) or (ret_val==False and len(images)>0):
                batch_boxes = get_yolo_boxes(infer_model, images, net_h, net_w, config['model']['anchors'], obj_thresh, nms_thresh)

                for i in range(len(images)):
                    draw_boxes(images[i], batch_boxes[i], config['model']['labels'], obj_thresh) 
                    cv2.imshow('video with bboxes', images[i])
                images = []
            if cv2.waitKey(1) == 27: 
                break  # esc to quit
        cv2.destroyAllWindows()        
    elif input_path[-4:].lower() == '.mp4': # do detection on a video
        video_out = output_path + input_path.split('/')[-1]
        video_reader = cv2.VideoCapture(input_path)

        nb_frames = int(video_reader.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_h = int(video_reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_w = int(video_reader.get(cv2.CAP_PROP_FRAME_WIDTH))
        fps = int(video_reader.get(cv2.CAP_PROP_FPS))

        video_writer = cv2.VideoWriter(video_out,
                               cv2.VideoWriter_fourcc(*'mp4v'),
                               fps,
                               (frame_w, frame_h))
        # the main loop
        batch_size  = 1
        images      = []
        start_point = 0 #%
        show_window = False
        for frame_num in tqdm(range(nb_frames)):
            _, image = video_reader.read()

            if (float(frame_num+1)/nb_frames) > start_point/100.:
                images += [image]

                if (frame_num%batch_size == 0) or (frame_num == (nb_frames-1) and len(images) > 0):
                    # predict the bounding boxes
                    batch_boxes = get_yolo_boxes(infer_model, images, net_h, net_w, config['model']['anchors'], obj_thresh, nms_thresh)

                    for i in range(len(images)):
                        # draw bounding boxes on the image using labels
                        for box in batch_boxes[i]:
                            # Only one class: licence_plate
                            if box.classes[0] > obj_thresh:
                                # Crop image to these coords
                                crop = images[i][box.ymin:box.ymax,
                                             box.xmin:box.xmax]

                                # Don't ask how a crop can have 0 in a
                                # dimension, but it does happen
                                if not any(x == 0 for x in crop.shape):
                                    # Preprocess licence plate to make OCR
                                    # easier
                                    grey = cv2.cvtColor(crop,
                                                        cv2.COLOR_BGR2GRAY)
                                    grey = cv2.resize(grey, None, fx=3, fy=3,
                                                      interpolation=cv2.INTER_CUBIC)
                                    blur = cv2.GaussianBlur(grey, (5,5), 0)
                                    blur2 = cv2.medianBlur(blur, 3)
                                    ret, thresh = cv2.threshold(blur2, 0, 255,
                                                                cv2.THRESH_OTSU)
                                    pred = pytesseract.image_to_string(thresh,
                                                                      lang="eng",
                                                                      config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ").strip()

                                    draw_box(images[i], box, pred)

                        # show the video with detection bounding boxes          
                        if show_window: cv2.imshow('video with bboxes', images[i])  

                        # write result to the output video
                        video_writer.write(images[i]) 
                    images = []
                if show_window and cv2.waitKey(1) == 27: break  # esc to quit

        if show_window: cv2.destroyAllWindows()
        video_reader.release()
        video_writer.release()       
    else: # do detection on an image or a set of images
        image_paths = []

        if os.path.isdir(input_path): 
            for inp_file in os.listdir(input_path):
                image_paths += [input_path + inp_file]
        else:
            image_paths += [input_path]

        image_paths = [inp_file for inp_file in image_paths if (inp_file[-4:] in ['.jpg', '.png', 'JPEG'])]

        # the main loop
        for image_path in image_paths:
            image = cv2.imread(image_path)
            print(image_path)

            # predict the bounding boxes
            boxes = get_yolo_boxes(infer_model, [image], net_h, net_w, config['model']['anchors'], obj_thresh, nms_thresh)[0]

            # Run OCR on bounding box
            for i, box in enumerate(boxes):
                # Only one class: licence_plate
                if box.classes[0] > obj_thresh:
                    # Crop image to these coords
                    crop = image[box.ymin:box.ymax,
                                 box.xmin:box.xmax]
                    raw = pytesseract.image_to_string(crop,
                                                      lang="eng",
                                                      config="--psm 7 --oem 3")
                    clean = raw.strip()
                    draw_box(image, box, clean)

            # write the image with bounding boxes to file
            cv2.imwrite(output_path + image_path.split('/')[-1], np.uint8(image))         

if __name__ == '__main__':
    argparser = argparse.ArgumentParser(description='Predict with a trained yolo model')
    argparser.add_argument('-c', '--conf', help='path to configuration file')
    argparser.add_argument('-i', '--input', help='path to an image, a directory of images, a video, or webcam')    
    argparser.add_argument('-o', '--output', default='output/', help='path to output directory')   
    
    args = argparser.parse_args()
    _main_(args)
