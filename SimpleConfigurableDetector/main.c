/****************************************************************************
 * main.c
 * openacousticdevices.info
 * June 2017
 *****************************************************************************/

#include <stdbool.h>
#include <string.h>
#include <math.h>

#include "audioMoth.h"

/* Useful macros */

#define DEFAULT_WAIT_INTERVAL               1

#define FLASH_LED(led, duration) { \
    AudioMoth_set ## led ## LED(true); \
    AudioMoth_delay(duration); \
    AudioMoth_set ## led ## LED(false); \
}

#define SAVE_SWITCH_POSITION_AND_POWER_DOWN(duration) { \
    *previousSwitchPosition = switchPosition; \
    AudioMoth_powerDownAndWake(duration, true); \
}

/* SRAM buffer constants */

#define NUMBER_OF_SAMPLES_IN_DMA_TRANSFER   1024

/* DC filter constant */

#define DC_BLOCKING_FACTOR                  0.995f

/* Useful math constants */

#define PI                                  3.14159265359f

/* DC filter variables */

static int8_t bitsToShift;

static int32_t previousSample;
static int32_t previousFilterOutput;


/* Goertzel filter variables */

static float_t coeff;
static float_t threshold;
static float_t factor;
static float_t previousPower;

/* DMA buffers */

static int16_t primaryBuffer[NUMBER_OF_SAMPLES_IN_DMA_TRANSFER];
static int16_t secondaryBuffer[NUMBER_OF_SAMPLES_IN_DMA_TRANSFER];


static volatile bool recordingCancelled;

/* USB configuration data structure */

#pragma pack(push, 1)

typedef struct {
  uint8_t gain;
  uint8_t clockDivider;
  uint8_t acquisitionCycles;
  uint8_t oversampleRate;
  uint32_t sampleRate;
  uint8_t sampleRateDivider;
  uint8_t enableLED;
  uint32_t goertzelFreq;
  float_t goertzelThresh;
  float_t goertzelFactor;
} configSettings_t;

#pragma pack(pop)

configSettings_t defaultConfigSettings = {
  .gain = 2,
  .clockDivider = 4,
  .acquisitionCycles = 16,
  .oversampleRate = 1,
  .sampleRate = 384000,
  .sampleRateDivider = 8,
  .enableLED = 1,
  .goertzelFreq = 1400,
  .goertzelThresh = 1000.0,
  .goertzelFactor = 0.99,
};

uint32_t *previousSwitchPosition = (uint32_t*)AM_BACKUP_DOMAIN_START_ADDRESS;

configSettings_t *configSettings = (configSettings_t*)(AM_BACKUP_DOMAIN_START_ADDRESS + 4);

/* Firmware version and description */

static uint8_t firmwareVersion[AM_FIRMWARE_VERSION_LENGTH] = {1, 0, 0};

static uint8_t firmwareDescription[AM_FIRMWARE_DESCRIPTION_LENGTH] = "Example-Firmware";

/* Required time zone handler */

void AudioMoth_timezoneRequested(int8_t *timezone) { }

/* Required interrupt handles */

void AudioMoth_handleSwitchInterrupt(void) {

  recordingCancelled = true;

}

void AudioMoth_handleMicrophoneInterrupt(int16_t sample) { }


/* Required USB message handlers */

void AudioMoth_usbFirmwareVersionRequested(uint8_t **firmwareVersionPtr) {

    *firmwareVersionPtr = firmwareVersion;

}

void AudioMoth_usbFirmwareDescriptionRequested(uint8_t **firmwareDescriptionPtr) {

    *firmwareDescriptionPtr = firmwareDescription;

}

void AudioMoth_usbApplicationPacketRequested(uint32_t messageType, uint8_t *transmitBuffer, uint32_t size) {

    memcpy(transmitBuffer + 1, configSettings, sizeof(configSettings_t));

    /* Copy the current time to the USB packet */

    uint32_t currentTime = AudioMoth_getTime();

    memcpy(transmitBuffer + 1, &currentTime, 4);

    /* Copy the unique ID to the USB packet */

    memcpy(transmitBuffer + 5, (uint8_t*)AM_UNIQUE_ID_START_ADDRESS, AM_UNIQUE_ID_SIZE_IN_BYTES);

    /* Copy the battery state to the USB packet */

    AM_batteryState_t batteryState = AudioMoth_getBatteryState();

    memcpy(transmitBuffer + 5 + AM_UNIQUE_ID_SIZE_IN_BYTES, &batteryState, 1);

    /* Copy the firmware version to the USB packet */

    memcpy(transmitBuffer + 6 + AM_UNIQUE_ID_SIZE_IN_BYTES, firmwareVersion, AM_FIRMWARE_VERSION_LENGTH);

    /* Copy the firmware description to the USB packet */

    memcpy(transmitBuffer + 6 + AM_UNIQUE_ID_SIZE_IN_BYTES + AM_FIRMWARE_VERSION_LENGTH, firmwareDescription, AM_FIRMWARE_DESCRIPTION_LENGTH);

}

void AudioMoth_usbApplicationPacketReceived(uint32_t messageType, uint8_t *receiveBuffer, uint8_t *transmitBuffer, uint32_t size) {

    /* Copy the USB packet contents to the back-up register data structure location */

    memcpy(configSettings, receiveBuffer + 1, sizeof(configSettings_t));

    /* Copy the back-up register data structure to the USB packet */

    memcpy(transmitBuffer + 1, configSettings, sizeof(configSettings_t));

}

/* Function prototypes */

static void filter(int16_t *source, uint8_t sampleRateDivider, uint32_t size);
static void startFilter(void);

/* Main function */

int main(void) {

    /* Initialise device */

    AudioMoth_initialise();

    /* Check the switch position */

    AM_switchPosition_t switchPosition = AudioMoth_getSwitchPosition();

    if (AudioMoth_isInitialPowerUp()) {

      *previousSwitchPosition = AM_SWITCH_NONE;

      memcpy(configSettings, &defaultConfigSettings, sizeof(configSettings_t));

    }

    if (switchPosition == AM_SWITCH_USB) {

        /* Handle the case that the switch is in USB position. Waits in low energy state until USB disconnected or switch moved  */

        AudioMoth_handleUSB();

        SAVE_SWITCH_POSITION_AND_POWER_DOWN(DEFAULT_WAIT_INTERVAL);

    } else if (switchPosition == AM_SWITCH_DEFAULT){

        /* Begin recording and filter. */

        startFilter();

        while (!recordingCancelled) {

            AudioMoth_setRedLED(true);
            AudioMoth_delay(1000);
            AudioMoth_setRedLED(false);
            AudioMoth_delay(1000);

        }

    } else {

        AudioMoth_setBothLED(true);
        AudioMoth_delay(10000);
        AudioMoth_setBothLED(false);

    }

    /* Power down and wake up in one second */

    AudioMoth_powerDownAndWake(1, true);

}

static void startFilter() {
    /* Calculate the bits to shift */

    bitsToShift = 0;

    uint16_t oversampling = configSettings->oversampleRate * configSettings->sampleRateDivider;

    while (oversampling > 16) {
      oversampling = oversampling >> 1;
      bitsToShift += 1;
    }

    float_t realSampleRate = (float_t)configSettings->sampleRate / (float_t)configSettings->sampleRateDivider;
    float_t targetSampleRate = (float_t)configSettings->goertzelFreq;

    /* Setup Goertzel filter coefficient */

    coeff = cos(2.0 * PI * (targetSampleRate / realSampleRate));
    threshold = configSettings->goertzelThresh;
    factor = configSettings->goertzelFactor;

    /* Initialise microphone for recording */

    AudioMoth_enableMicrophone(configSettings->gain, configSettings->clockDivider, configSettings->acquisitionCycles, configSettings->oversampleRate);

    AudioMoth_initialiseDirectMemoryAccess(primaryBuffer, secondaryBuffer, NUMBER_OF_SAMPLES_IN_DMA_TRANSFER);

    AudioMoth_startMicrophoneSamples(configSettings->sampleRate);

}


void AudioMoth_handleDirectMemoryAccessInterrupt(bool isPrimaryBuffer, int16_t **nextBuffer) {

  int16_t *source = secondaryBuffer;

  if (isPrimaryBuffer) source = primaryBuffer;

  /* Update the current buffer index and write buffer */

  filter(source, configSettings->sampleRateDivider, NUMBER_OF_SAMPLES_IN_DMA_TRANSFER);

}

static void filter(int16_t *source, uint8_t sampleRateDivider, uint32_t size) {

    int32_t filteredOutput;
    int32_t scaledPreviousFilterOutput;
    float_t power, newPower;

    float_t s0, s1, s2;

    s0 = s1 = 0;

    for (int i = 0; i < size; i += sampleRateDivider) {

        int32_t sample = 0;

        for (int j = 0; j < sampleRateDivider; j += 1) {

            sample += source[i + j];

        }

        if (bitsToShift > 0) {

            sample = sample >> bitsToShift;

        }

        scaledPreviousFilterOutput = (int32_t)(DC_BLOCKING_FACTOR * previousFilterOutput);

        filteredOutput = sample - previousSample + scaledPreviousFilterOutput;

        previousFilterOutput = filteredOutput;

        previousSample = sample;

        /* Goertzel filter calculations */

        s2 = ( (float_t)(int16_t)filteredOutput / (float_t)INT16_MAX ) + coeff * s1 - s0;
        s0 = s1;
        s1 = s2;

    }

    newPower = s1 * s1 + s0 * s0 - coeff * s1 * s0;
    power = factor * newPower + (1 - factor) * previousPower;

    if (power >= threshold) {

        AudioMoth_setGreenLED(true);

    } else {

        AudioMoth_setGreenLED(false);

    }

    previousPower = power;

}
