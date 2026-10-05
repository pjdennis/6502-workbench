# The text mode's font (rtl/text_render.v includes it): generated from firmware/lib/graphics/font_12x16.txt by
# tools/font_12x16.py into hardware/michael/fpga/build/. Include after TB_PASS is set; designs that use the text
# renderer add $(FONT_VH) to their synthesis inputs' prerequisites.
TEXT_MK_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
REPO_DIR    := $(abspath $(TEXT_MK_DIR)../../..)
FONT_VH     := $(TEXT_MK_DIR)build/font_12x16.vh

$(FONT_VH): $(REPO_DIR)/firmware/lib/graphics/font_12x16.txt $(REPO_DIR)/tools/font_12x16.py
	python3 $(REPO_DIR)/tools/font_12x16.py vh $@

$(TB_PASS): $(FONT_VH)
