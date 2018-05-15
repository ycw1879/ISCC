#!/usr/bin/env python

import rospy
import tensorflow as tf
import sys
import cv2
import time
import numpy as np
from PIL import Image
import io
from race.msg import sign_classes
from std_msgs.msg import Bool
from std_msgs.msg import Int16

sc_onoff = True
prev_onoff = True

labels = ['no sign', 'crosswalk', 'static obstacle', 'dynamic obstacle', 'branch road', 'curve', 'uturn', 'parking']
buff = ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]

cam = cv2.VideoCapture()
cnt = 0
step = 0

def crop_sign(image):
    cv_image = image
    (rows, cols, channels) = cv_image.shape

    #imCrop2 = cv_image[0:240,400:640]
    imCrop2 = cv_image

    hsv = cv2.cvtColor(imCrop2, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([90, 70, 50])
    upper_blue = np.array([120, 255, 255])
    lower_red = np.array([0, 50, 0])
    upper_red = np.array([10, 255, 255])
    lower_red2 = np.array([160, 50, 0])
    upper_red2 = np.array([180, 255, 255])
    mask_b = cv2.inRange(hsv, lower_blue, upper_blue)
    mask_r1 = cv2.inRange(hsv, lower_red, upper_red)
    mask_r2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_r = mask_r1 + mask_r2
    mask = mask_r + mask_b

    image, contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
																																	
    if (len(contours) > 0):
        max_area = 0
        ci = 0

        for i in range(len(contours)):
            cnt = contours[i]
            area = cv2.contourArea(cnt)

            if (area > max_area):
                max_area = area
                ci = i

        cnt = contours[ci]

        epsilon = 0.1 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        x, y, w, h = cv2.boundingRect(approx)

        if w > 30 and h > 30 and w / h >= 0.4 and w / h <= 2.0:
            for i in range(0, 7) :
                mask = cv2.dilate(mask, np.ones((int(w/10), int(h/10)), np.uint8), iterations=1)

            for i in range(0, 7) :
                mask = cv2.erode(mask, np.ones((int(w/10), int(h/10)), np.uint8), iterations=1)

            imCrop2 = cv2.bitwise_and(imCrop2, imCrop2, mask=mask)

            a = y
            b = y + h
            c = x
            d = x + w
            imCrop = imCrop2[a:b, c:d]

            return imCrop

def talker(classification) :
	if not rospy.is_shutdown():
		rospy.loginfo(classification)
		ret = labels.index(classification)
		if(ret != 0) :
			pub.publish(ret)

def sc_onoffCallback(data) :
	global prev_onoff, sc_onoff, cam
	sc_onoff = data.data
	if(prev_onoff != sc_onoff) :
		prev_onoff = sc_onoff
		if(sc_onoff) :
			print("SC ON")
			cam.open(0)
		else :
			print("SC OFF")
			cam.release()


if __name__ == '__main__' :
	pub = rospy.Publisher('/sign_classes', Int16, queue_size = 10)
	rospy.init_node('sign_detector')
	rospy.Subscriber("sc_onoff", Bool, sc_onoffCallback)
	rate = rospy.Rate(10)
	cam.open(0)
	try :
		with tf.gfile.FastGFile("work/signs/retrained_graph_v2.pb", 'rb') as f:
    			graph_def = tf.GraphDef()		
    			graph_def.ParseFromString(f.read())
    			_ = tf.import_graph_def(graph_def, name='')

		with tf.Session() as sess:
			label_lines = [line.rstrip() for line in tf.gfile.GFile("work/signs/retrained_labels.txt")]
			softmax_tensor = sess.graph.get_tensor_by_name('final_result:0')
    			
			while True:
				if(not sc_onoff or not cam.isOpened()) :
					continue
        			ret_val, img = cam.read()
        			img = cv2.flip(img, 0)
        			img = cv2.flip(img, 1)

				cv2.imshow("origin", img)
        			img = img[50:300, 150:550]
				
        			img_crop = crop_sign(img)
				
        			if img_crop is None :
					img_crop = img	
				cv2.imshow("ROI", img)

        			if ret_val:
            				predictions = sess.run(softmax_tensor, {'DecodeJpeg:0': img})

            				top_k = predictions[0].argsort()[-len(predictions[0]):][::-1]			
            				max_score = 0

            				prediction = ""

					for node_id in top_k:
                				human_string = label_lines[node_id]
                				score = predictions[0][node_id]

						#if score < 0.4:
						#	continue
						
			        	        if score > max_score :
							prediction = human_string
					                max_score = score  
					if not prediction == 'no sign' :
						buff[step % 15] = prediction 
	    					step = step + 1

	    				count = 0
					print(prediction)
	    				for i in range(0, 15) :
						if buff[i] == prediction :
							count = count + 1	

					if count >= 3 :
						print('%s (score = %.5f)' % (prediction, max_score))
						talker(prediction)
						for i in range(0, 15) :
							buff[i] = ""
            				print()
				if cv2.waitKey(1) & 0xFF == ord('q'):
					break
				rate.sleep()
	
	except rospy.ROSInterruptException: pass

