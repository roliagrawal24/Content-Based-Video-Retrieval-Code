import csv
import math
import os

import cv2
from matplotlib import pyplot as plt
import numpy as np
from scipy.stats import energy_distance, wasserstein_distance

import app.config as config
from app.helpers import get_video_filenames, print_terminal_table
from app.video_operations import ClickAndDrop


class HistogramGenerator:
    colours = ('b', 'g', 'r')
    bins = (8, 12, 3)  # 8 hue bins, 12 saturation bins, 3 value bins
    histcmp_methods = [cv2.HISTCMP_CORREL, cv2.HISTCMP_CHISQR, cv2.HISTCMP_INTERSECT, cv2.HISTCMP_BHATTACHARYYA,
                       cv2.HISTCMP_CHISQR_ALT, cv2.HISTCMP_KL_DIV]
    histcmp_3d_methods = ["wasserstein_distance", "energy_distance"]
    histogram_comparison_weigths = {  # weights per comparison methods
        'gray': 1,
        'rgb': 5,
        'hsv': 8
    }
    results_array = list()

    def __init__(self, directory, file_name):
        """
        Initialise variables and create a VideoCapture object for a mp4 file.
        :param directory: the directory where the video file is located
        :param file_name: the mp4 video file's name
        """
        self.directory = directory
        self.file_name = file_name

        # start capturing video
        self.video_capture = cv2.VideoCapture("{}{}".format(self.directory, self.file_name))
        self.check_video_capture()

        # read the video and store the histograms for each frame per color channel in a dict
        self.histograms_gray_dict = list()
        self.histograms_rgb_dict = {
            'b': list(),
            'g': list(),
            'r': list()
        }
        self.histograms_hsv_dict = list()

        # keep current ROI for re-use
        self.reference_points = list()

    def generate_video_rgb_histogram(self, is_query=False, cur_ref_points=None):
        """
        Generates multiple normalized histograms (one every second) for a video.
        :param is_query: boolean specifying if the input video is the query video (to select ROI)
        :param cur_ref_points: list of previously-used ROI point locations
        :return: None
        """
        # determine which frames to process for histograms
        frames_to_process = _get_frames_to_process(self.video_capture)

        frame_counter = 0  # keep track of current frame ID to know to process it or not
        while self.video_capture.isOpened():
            ret, frame = self.video_capture.read()  # read capture frame by frame
            if ret:
                if is_query and frame_counter == 0:
                    if cur_ref_points is None:
                        cad = ClickAndDrop(frame)
                        if config.debug:  # show the cropped region of interest
                            roi_frame = cad.get_roi()
                            cv2.imshow('Selected ROI', roi_frame)
                            cv2.waitKey(0)
                        self.reference_points = cad.get_reference_points()
                    else:
                        self.reference_points = cur_ref_points
                frame_counter += 1
                if frame_counter in frames_to_process:
                    for i, col in enumerate(self.colours):
                        if is_query and len(self.reference_points) == 2:
                            roi = frame[self.reference_points[0][1]:self.reference_points[1][1],
                                        self.reference_points[0][0]:self.reference_points[1][0]]
                            histogram = cv2.calcHist([roi], [i], None, [256], [0, 256])
                        else:
                            histogram = cv2.calcHist([frame], [i], None, [256], [0, 256])
                        histogram = cv2.normalize(histogram, histogram)
                        self.histograms_rgb_dict[col].append(histogram)
                        if config.debug:  # show individual BGR histogram plots
                            print("i: {}, col: {}".format(i, col))
                            plt.plot(histogram, color=col)
                            plt.xlim([0, 256])
                    if config.debug:
                        plt.show()

                    # user exit on "q" or "Esc" key press
                    k = cv2.waitKey(30) & 0xFF
                    if k == 25 or k == 27:
                        break
            else:
                break
        self.generate_and_store_average_rgb_histogram()
        self.destroy_video_capture()

    def generate_video_grayscale_histogram(self, is_query=False):
        """
        Generates multiple normalized grayscale histograms (one every second) for a video.
        :param is_query: boolean specifying if the input video is the query video (to select ROI)
        :return: None
        """
        # determine which frames to process for histograms
        frames_to_process = _get_frames_to_process(self.video_capture)

        frame_counter = 0  # keep track of current frame ID to know to process it or not
        while self.video_capture.isOpened():
            ret, frame = self.video_capture.read()  # read capture frame by frame
            if ret:
                if is_query and frame_counter == 0:
                    cad = ClickAndDrop(frame)
                    if config.debug:  # show the cropped region of interest
                        roi_frame = cad.get_roi()
                        cv2.imshow("Selected ROI", roi_frame)
                        cv2.waitKey(0)
                    self.reference_points = cad.get_reference_points()
                frame_counter += 1
                if frame_counter in frames_to_process:
                    if is_query and len(self.reference_points) == 2:
                        roi = frame[self.reference_points[0][1]:self.reference_points[1][1],
                                    self.reference_points[0][0]:self.reference_points[1][0]]
                        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                        histogram = cv2.calcHist([roi_gray], [0], None, [256], [0, 256])
                    else:
                        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        histogram = cv2.calcHist([gray_frame], [0], None, [256], [0, 256])
                    histogram = cv2.normalize(histogram, histogram)
                    self.histograms_gray_dict.append(histogram)
                    if config.debug:  # show individual grayscale histogram plots
                        plt.figure()
                        plt.title("{} frame {}".format(self.file_name, frame_counter))
                        plt.xlabel("Bins")
                        plt.plot(histogram)
                        plt.xlim([0, 256])
                        plt.show()

                    # user exit on "q" or "Esc" key press
                    k = cv2.waitKey(30) & 0xFF
                    if k == 25 or k == 27:
                        break
            else:
                break
        self.generate_and_store_average_grayscale_histogram()
        self.destroy_video_capture()

    def generate_video_hsv_histogram(self, is_query=False, cur_ref_points=None):
        """
        Generates multiple normalized HSV histograms (one every second) for a video.
        :param is_query: boolean specifying if the input video is the query video (to select ROI)
        :param cur_ref_points: list of previously-used ROI point locations
        :return: None
        """
        # determine which frames to process for histograms
        frames_to_process = _get_frames_to_process(self.video_capture)

        frame_counter = 0  # keep track of current frame ID to know to process it or not
        while self.video_capture.isOpened():
            ret, frame = self.video_capture.read()  # read capture frame by frame
            if ret:
                if is_query and frame_counter == 0:
                    if cur_ref_points is None:
                        cad = ClickAndDrop(frame)
                        if config.debug:  # show the cropped region of interest
                            roi_frame = cad.get_roi()
                            cv2.imshow("Selected ROI", roi_frame)
                            cv2.waitKey(0)
                        self.reference_points = cad.get_reference_points()
                    else:
                        self.reference_points = cur_ref_points
                frame_counter += 1
                if frame_counter in frames_to_process:
                    if is_query and len(self.reference_points) == 2:
                        roi = frame[self.reference_points[0][1]:self.reference_points[1][1],
                                    self.reference_points[0][0]:self.reference_points[1][0]]
                        roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                        histogram = cv2.calcHist([roi_hsv], [0, 1, 2], None, self.bins, [0, 180, 0, 256, 0, 256])
                    else:
                        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                        histogram = cv2.calcHist([hsv_frame], [0, 1, 2], None, self.bins, [0, 180, 0, 256, 0, 256])
                    histogram = cv2.normalize(histogram, histogram)
                    self.histograms_hsv_dict.append(histogram)
                    if config.debug:  # show individual HSV histogram plots
                        plt.imshow(histogram)
                        plt.title("{} frame {}".format(self.file_name, frame_counter))
                        plt.show()

                    # user exit on "q" or "Esc" key press
                    k = cv2.waitKey(30) & 0xFF
                    if k == 25 or k == 27:
                        break
            else:
                break
        self.generate_and_store_average_hsv_histogram()
        self.destroy_video_capture()

    def generate_and_store_average_rgb_histogram(self):
        """
        Generates a single BGR histogram by averaging all histograms of a video before writing the results to a txt
        file.
        :return: None
        """
        avg_histogram = np.zeros(shape=(255, 1))  # array to store average histogram values
        for col, hists in self.histograms_rgb_dict.items():
            for i in range(0, 255):  # loop through all bins
                bin_sum = 0

                # get value for each colour histogram in bin i
                for arr_index in range(0, len(hists)):
                    bin_value = hists[arr_index].item(i)
                    bin_sum += bin_value

                # average all bins values to store in new histogram
                new_bin_value = bin_sum / len(hists)
                avg_histogram[i] = new_bin_value

            if not os.path.exists("../histogram_data/{}/".format(self.file_name)):
                os.makedirs("../histogram_data/{}/".format(self.file_name))
            np.savetxt("../histogram_data/{}/hist-{}".format(self.file_name, col), avg_histogram, fmt='%f')
            if config.show_histograms:
                plt.plot(avg_histogram, color=col)
                plt.xlim([0, 256])
        if config.show_histograms:
            plt.title("RGB histogram for '{}'".format(self.file_name))
            plt.xlabel("Bins")
            plt.show()

    def generate_and_store_average_grayscale_histogram(self):
        """
        Generates a single BGR histogram by averaging all histograms of a video before writing the results to a txt
        file.
        :return: None
        """
        avg_histogram = np.zeros(shape=(255, 1))  # array to store average histogram values

        col = "gray"
        hist = self.histograms_gray_dict

        for i in range(0, 255):  # loop through all bins
            bin_sum = 0

            # get value for each colour histogram in bin i
            for arr_index in range(0, len(hist)):
                bin_value = hist[arr_index].item(i)
                bin_sum += bin_value

            # average all bins values to store in new histogram
            new_bin_value = bin_sum / len(hist)
            avg_histogram[i] = new_bin_value

        if not os.path.exists("../histogram_data/{}/".format(self.file_name)):
            os.makedirs("../histogram_data/{}/".format(self.file_name))
        np.savetxt("../histogram_data/{}/hist-{}".format(self.file_name, col), avg_histogram, fmt='%f')
        if config.show_histograms:
            plt.plot(avg_histogram, color=col)
            plt.xlim([0, 256])
            plt.title("Grayscale histogram for '{}'".format(self.file_name))
            plt.xlabel("Bins")
            plt.show()

    def generate_and_store_average_hsv_histogram(self):
        """
        Generates a single BGR histogram by averaging all histograms of a video before writing the results to a txt
        file.
        :return: None
        """
        avg_histogram = np.zeros(shape=(8, 12, 3))  # array to store average histogram values

        col = "hsv"
        hist = self.histograms_hsv_dict

        for h in range(0, self.bins[0]):  # loop through hue bins
            for s in range(0, self.bins[1]):  # loop through saturation bins
                for v in range(0, self.bins[2]):  # loop through value bins
                    bin_sum = 0

                    # get value for each colour histogram in bin [h][s][v]
                    for arr_index in range(0, len(hist)):
                        bin_value = hist[arr_index][h][s][v]
                        bin_sum += bin_value

                    # average all bins values to store in new histogram
                    new_bin_value = bin_sum / len(hist)
                    avg_histogram[h][s][v] = new_bin_value

        if not os.path.exists("../histogram_data/{}/".format(self.file_name)):
            os.makedirs("../histogram_data/{}/".format(self.file_name))
        with open("../histogram_data/{}/hist-{}".format(self.file_name, col), 'w') as file:
            file.write("# HSV Histogram shape: {0}\n".format(avg_histogram.shape))
            for arr_2d in avg_histogram:
                np.savetxt(file, arr_2d)
                file.write("# New slice\n")

        if config.show_histograms:
            plt.imshow(avg_histogram)
            plt.title("HSV histogram for '{}'".format(self.file_name))
            plt.show()

    def match_histograms(self, cur_all_model='all'):
        """
        Compares the BGR histogram of the recorded video and compares it with each of the saved average BGR histograms
        using different histogram matching methods such as the Chi-Square or Bhattacharyya methods, and prints the
        results as probabilities in a CLI table and writes the data to a CSV file.
        :return: None
        """
        # variables used for finding the match to the recorded video
        video_match = ""
        video_match_value = 0

        # get histogram for the recorded video to match - todo: calculate the histogram on the go
        hist_recording = dict()
        if config.model == "gray" or (cur_all_model == "gray" and config.model == "all"):
            hist_recording = {
                'gray': np.loadtxt("../histogram_data/{}/hist-gray".format(self.file_name), dtype=np.float32, unpack=False),
            }
        elif config.model == "rgb" or (cur_all_model == "rgb" and config.model == "all"):
            hist_recording = {
                'b': np.loadtxt("../histogram_data/{}/hist-b".format(self.file_name), dtype=np.float32, unpack=False),
                'g': np.loadtxt("../histogram_data/{}/hist-g".format(self.file_name), dtype=np.float32, unpack=False),
                'r': np.loadtxt("../histogram_data/{}/hist-r".format(self.file_name), dtype=np.float32, unpack=False)
            }
        elif config.model == "hsv" or (cur_all_model == "hsv" and config.model == "all"):
            hsv_data = np.loadtxt("../histogram_data/{}/hist-hsv".format(self.file_name))
            hist_recording = {
                'hsv': hsv_data.reshape((8, 12, 3))
            }

        # compare recorded video histogram with histogram of each video
        print("\n{} Histogram Comparison Results:\n".format(_get_chosen_model_string(cur_all_model)))

        method = ""
        field_names = ["video", "score"]

        # use OpenCV's compareHist function for RGB and gray scale histograms (works with 2d arrays only)
        if config.model == "rgb" or config.model == "gray" or (cur_all_model == "gray" and config.model == "all") or (cur_all_model == "rgb" and config.model == "all"):
            for m in self.histcmp_methods:
                if m == 0:
                    method = "CORRELATION"
                elif m == 1:
                    method = "INTERSECTION"
                elif m == 2:
                    method = "CHI SQUARE"
                elif m == 3:
                    method = "BHATTACHARYYA"
                elif m == 4:
                    method = "ALTERNATIVE CHI-SQUARE"
                elif m == 5:
                    method = "KULLBACK-LEIBLER DIVERGENCE"

                # CSV file to write data to for each method
                if config.model == "all":
                    csv_file = open('../results/csv/{}-{}-{}.csv'.format(config.model, cur_all_model, method), 'w')
                else:
                    csv_file = open('../results/csv/{}-{}.csv'.format(config.model, method), 'w')
                with csv_file:
                    writer = csv.DictWriter(csv_file, fieldnames=field_names)
                    writer.writeheader()

                    table_data = list()
                    for i, file in enumerate(get_video_filenames("../footage/")):
                        comparison = 0
                        if config.model == "gray" or (cur_all_model == "gray" and config.model == "all"):
                            hist_gray = np.loadtxt("../histogram_data/{}/hist-gray".format(file), dtype=np.float32, unpack=False)
                            comparison = cv2.compareHist(hist_recording['gray'], hist_gray, m)
                        elif config.model == "rgb" or (cur_all_model == "rgb" and config.model == "all"):
                            hist_b = np.loadtxt("../histogram_data/{}/hist-b".format(file), dtype=np.float32, unpack=False)
                            hist_g = np.loadtxt("../histogram_data/{}/hist-g".format(file), dtype=np.float32, unpack=False)
                            hist_r = np.loadtxt("../histogram_data/{}/hist-r".format(file), dtype=np.float32, unpack=False)
                            comparison_b = cv2.compareHist(hist_recording['b'], hist_b, m)
                            comparison_g = cv2.compareHist(hist_recording['g'], hist_g, m)
                            comparison_r = cv2.compareHist(hist_recording['r'], hist_r, m)
                            comparison = (comparison_b + comparison_g + comparison_r) / 3

                        # append data to table
                        table_data.append([file, round(comparison, 5)])

                        # write data to CSV file
                        writer.writerow({'video': file, 'score': round(comparison, 5)})

                        if i == 0:
                            video_match = file
                            video_match_value = comparison
                        else:
                            # correlation and intersection
                            if m in [0, 2] and comparison > video_match_value:
                                video_match = file
                                video_match_value = comparison
                            # chi-square, alternative chi-square, bhattacharyya and Kullback-Leibler divergence
                            elif m in [1, 3, 4, 5] and comparison < video_match_value:
                                video_match = file
                                video_match_value = comparison

                # append video match found to results list (using weights)
                if cur_all_model == "gray":
                    for _ in range(0, self.histogram_comparison_weigths['gray'], 1):
                        self.results_array.append(video_match)
                elif cur_all_model == "rgb":
                    for _ in range(0, self.histogram_comparison_weigths['rgb'], 1):
                        self.results_array.append(video_match)

                print_terminal_table(table_data, method)
                print("{} {} match found: ".format(_get_chosen_model_string(cur_all_model), method) +
                      "\x1b[1;31m" + video_match + "\x1b[0m" + "\n\n")

        # use SciPy's statistical distances functions for HSV histograms (compareHist does not work with 3d arrays)
        elif config.model == "hsv" or config.model == "all":
            for m in self.histcmp_3d_methods:
                if m == "wasserstein_distance":
                    method = "WASSERSTEIN DISTANCE (EMD)"
                elif m == "energy_distance":
                    method = "ENERGY DISTANCE"

                # CSV file to write data to for each method
                if config.model == "all":
                    csv_file = open('../results/csv/{}-{}-{}.csv'.format(config.model, cur_all_model, method), 'w')
                else:
                    csv_file = open('../results/csv/{}-{}.csv'.format(config.model, method), 'w')
                with csv_file:

                    writer = csv.DictWriter(csv_file, fieldnames=field_names)
                    writer.writeheader()

                    table_data = list()
                    for i, file in enumerate(get_video_filenames("../footage/")):
                        hist_hsv_data = np.loadtxt("../histogram_data/{}/hist-hsv".format(file))
                        hist_hsv = hist_hsv_data.reshape((8, 12, 3))
                        comparison = 0
                        for h in range(0, self.bins[0]):  # loop through hue bins
                            for s in range(0, self.bins[1]):  # loop through saturation bins
                                hist_recording_slice = hist_recording['hsv'][h][s]
                                hist_hsv_slice = hist_hsv[h][s]
                                if method == "WASSERSTEIN DISTANCE (EMD)":
                                    comparison += wasserstein_distance(hist_recording_slice, hist_hsv_slice)
                                elif method == "ENERGY DISTANCE":
                                    comparison += energy_distance(hist_recording_slice, hist_hsv_slice)

                        # append data to table
                        table_data.append([file, round(comparison, 5)])

                        # write data to CSV file
                        writer.writerow({'video': file, 'score': round(comparison, 5)})

                        if i == 0:
                            video_match = file
                            video_match_value = comparison
                        else:
                            if comparison < video_match_value:
                                video_match = file
                                video_match_value = comparison

                # append video match found to results list (using weights)
                for _ in range(0, self.histogram_comparison_weigths['hsv']):
                    self.results_array.append(video_match)

                print_terminal_table(table_data, method)
                print("{} {} Match found: ".format(_get_chosen_model_string(cur_all_model), method) +
                      "\x1b[1;31m" + video_match + "\x1b[0m" + "\n\n")

    def rgb_histogram_shot_boundary_detection(self):
        """
        Compares consecutive frames' RGB histograms using the Kullback-Leibler Divergence metric. If the metric is
        bigger than the specified threshold, then a shot boundary has been detected.
        :return: None
        """
        threshold = 10
        x_axis = list()
        y_axis = list()
        is_under_threshold = True

        ret, frame = self.video_capture.read()  # get initial frame

        frame_counter = 0  # keep track of current frame ID to locate shot boundaries
        while self.video_capture.isOpened():
            prev_frame = frame[:]  # previous frame
            ret, frame = self.video_capture.read()  # read capture frame by frame

            if ret:
                frame_counter += 1
                cur_rgb_hist = {
                    'b': list(),
                    'g': list(),
                    'r': list()
                }
                prev_rgb_hist = {
                    'b': list(),
                    'g': list(),
                    'r': list()
                }
                for i, col in enumerate(self.colours):
                    # calculate RGB histograms
                    cur_frame_hist = cv2.calcHist([frame], [i], None, [256], [0, 256])
                    prev_frame_hist = cv2.calcHist([prev_frame], [i], None, [256], [0, 256])

                    # normalize histograms
                    cur_frame_hist = cv2.normalize(cur_frame_hist, cur_frame_hist)
                    prev_frame_hist = cv2.normalize(prev_frame_hist, prev_frame_hist)

                    # save histograms in dict
                    cur_rgb_hist[col].append(cur_frame_hist)
                    prev_rgb_hist[col].append(prev_frame_hist)

                # calculate Kullback-Leibler Divergence between consecutive frames
                comparison_r = cv2.compareHist(prev_rgb_hist['r'][0], cur_rgb_hist['r'][0], cv2.HISTCMP_KL_DIV)
                comparison_g = cv2.compareHist(prev_rgb_hist['g'][0], cur_rgb_hist['g'][0], cv2.HISTCMP_KL_DIV)
                comparison_b = cv2.compareHist(prev_rgb_hist['b'][0], cur_rgb_hist['b'][0], cv2.HISTCMP_KL_DIV)
                comparison = (comparison_b + comparison_g + comparison_r) / 3

                # append data to lists for plot
                x_axis.append(frame_counter)
                y_axis.append(comparison)

                if comparison > threshold and is_under_threshold:
                    is_under_threshold = False
                    print("Scene Change detected at Frame {}".format(frame_counter))
                elif comparison < threshold:
                    is_under_threshold = True

            else:
                break

        # Plot results
        plt.plot(x_axis, y_axis)
        plt.plot(x_axis, np.full(frame_counter, 10))
        plt.title("Kullback-Leibler Divergence Between Consecutive Frame RGB Histogram")
        plt.xlabel("Frame")
        plt.ylabel("KL Divergence")
        plt.show()

        self.destroy_video_capture()

    def check_video_capture(self):
        """
        Checks if the VideoCapture object was correctly created.
        :return: None
        """
        if not self.video_capture.isOpened():
            print("Error opening video file")

    def destroy_video_capture(self):
        """
        Tidying up the OpenCV environment and the video capture
        :return: None
        """
        self.video_capture.release()
        cv2.destroyAllWindows()

    def get_video_capture(self):
        """
        Returns the full VideoCapture object.
        :return: the VideoCapture object
        """
        return self.video_capture

    def get_current_reference_points(self):
        """
        Returns the current ROI point locations manually selected for the first frame for future re-use.
        :return: the ROI pixel locations retrieved from the first frame of the video
        """
        return self.reference_points

    def get_results_array(self):
        """
        Returns the array with the resulting video results.
        :return: array of strings
        """
        return self.results_array


def _get_frames_to_process(vc):
    """
    Returns the IDs of the frames to calculate a BGR histogram for.
    :param vc: the VideoCapture object to process
    :return: a list of integers representing the frames to process
    """
    frame_ids = list()
    total_frames = vc.get(cv2.CAP_PROP_FRAME_COUNT)
    fps = vc.get(cv2.CAP_PROP_FPS)
    for i in range(1, int(total_frames) + 1, math.ceil(fps)):
        frame_ids.append(i)
    return frame_ids


def _get_chosen_model_string(model):
    """
    Returns the Histogram Model chosen for the matching process.
    :return: a string representing the chosen histogram model
    """
    if model == "gray":
        return "Grayscale"
    elif model == "rgb":
        return "RGB"
    elif model == 'hsv':
        return "HSV"
    else:
        if config.model == "gray":
            return "Grayscale"
        elif config.model == "rgb":
            return "RGB"
        elif config.model == 'hsv':
            return "HSV"
