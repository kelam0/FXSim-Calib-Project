# -*- coding: utf-8 -*-
"""
Soluce pour FX calib, sim and pricing

M.Jawad - 04/01/2018

"""
import datetime
import pandas as pd
import numpy as np
import scipy as sp
from scipy import linalg

from matplotlib import pyplot as plt

Path = "C:\\Users\\Malek\\Documents\\Python Projects\\FXSim-Calib-Project\\"
startDate = datetime.date(2015,1,2)
endDate = datetime.date(2015,12,31)

def daterange(start_date, end_date):
    for n in range(int ((end_date - start_date).days)):
        yield start_date + datetime.timedelta(n)

NbSims = 1000
SimLength = 365

def FXSim(fxspot, vol, rdm, time):
    """
    FX simulation for n days with x vol using the random numbers provided over the "time" horizon
    """
    # create an array of lenght NbSims x "time" horizon
    sim = np.zeros((NbSims,len(time)))
    # simulate a random walk FX with no IR discounting
    for i in range(0,NbSims):
        for j in range(0,len(time)):
            #sim[i,j] = fxspot+time[j]*(vol)*rdm[i,j]*10/2 # percentage divide by 2 (xccy)
            sim[i,j] = fxspot+np.sqrt(time[j])*(vol)*rdm[i,j]
    # return simulation
    return sim

## issue with FXSim model is for very short periods, we underestimate the risk associated with FX fwds.
## lets get another vol dataframe maybe? with a 1m vol floored with the 1y vol applied to the front of the sims?

## otherwise change the simulation model with linear waiting of time?
## e.g. switch to np.sqrt(time) ? means that volatilities are applied faster over the 1st half of the year?

def SimulateFXRates(FilePath, SD, ED, NbSimulations, SimHorizon):
    """
    main function to simulate FX rates for each day
    input is csv file path, startdate, enddate, Number of simulations and simHorizon (nb of days)
    
    output 1 is a 4 dimension numpy array shaped by n days, currencyIndex, Nb simulations,  simHorizon (nb of days)
    output 2 is the currency list as reference
    output 3 is a dataframe of dates for reference for valuation
    """
    
    # load historical timeseries
    dateparse = lambda x: pd.datetime.strptime(x, '%d/%m/%Y')
    df = pd.read_csv(FilePath, parse_dates=['DATE'], date_parser=dateparse)

    # setup sim variables
    SimCalibration = (ED - SD).days
    time_array = np.linspace(0,1,SimCalibration)
    CcyList = list(df)[1:]
    
    # generate log returns dateframe and rolling volatility over the length of the calibration period
    df_LogR = np.log(df.loc[:,CcyList]) - np.log(df.loc[:,CcyList].shift(1))
    df_Vol = df_LogR.rolling(SimCalibration, SimCalibration).std()*sp.sqrt(SimCalibration)
    df_Vol = pd.concat([df.loc[:,['DATE']],df_Vol], axis=1)

    dateRange = [df_Vol.index[df_Vol['DATE'] == SD].tolist()[0], df_Vol.index[df_Vol['DATE'] == ED].tolist()[0]]
    SimArray = np.zeros((dateRange[1]-dateRange[0]+1,len(CcyList),NbSimulations,len(time_array)))
    # generate daily FX simulations over 1 year
    for n in range(dateRange[0],dateRange[1]+1):
        
        # generate the correlation matrix from the log return dataframe for each day
        df_Corr = df_LogR.loc[(n-dateRange[0]):n,CcyList].corr(method='pearson')
        
        # generate for every n day correlated random numbers til the SimHorizon
        CorrRdm = np.zeros((len(CcyList),NbSimulations,SimHorizon))
        for j in range(0, SimHorizon):
            CorrRdm[:,:,j] = np.dot(linalg.cholesky(df_Corr) , np.random.normal(0, 1, size=(len(CcyList),NbSimulations)))
            
        # generate FX simulations for every n day using the Correlated Random numbers generate before
        for ccy in CcyList:
            ccyI = CcyList.index(ccy)
            SimArray[n-dateRange[0],ccyI,:,:] = FXSim(df.loc[n, ccy], df_Vol.loc[n,ccy], CorrRdm[ccyI,:,:], time_array)           

    return [SimArray, CcyList, df.loc[:,['DATE']]]


# define a trade class
class FXfwdTrade:
    def __init__(self,TradeStart,MatDate,RecNot,RecCcy,PayNot,PayCcy):
        self.TradeStartDate = TradeStart
        self.maturityDate = MatDate   
        self.RecLegNotional = RecNot
        self.RecLegCcy = RecCcy
        self.RecLegCFDate = self.maturityDate
        self.PayLegNotional = PayNot
        self.PayLegCcy = PayCcy
        self.PayLegCFDate = self.maturityDate  

    def GenerateMTF(self, BatchDate, Dates, CcyList, Sims):
        if np.datetime64(startDate) in Dates.values and np.datetime64(BatchDate) in Dates.values:
            if BatchDate > self.maturityDate:
                self.MTF = np.zeroes((NbSims,len(CcyList)))
                            
            BatchStartIndex = Dates.index[Dates['DATE'] == startDate].tolist()[0]
            BatchIndex = Dates.index[Dates['DATE'] == BatchDate].tolist()[0] - BatchStartIndex
            #TradeStartIndex = Dates.index[Dates['DATE'] == self.TradeStartDate].tolist()[0] - BatchStartIndex
            #TradeEndIndex = Dates.index[Dates['DATE'] == self.maturityDate].tolist()[0] - BatchStartIndex
            MaturityIndex = (self.maturityDate - BatchDate).days
            SimShape = np.shape(Sims[BatchIndex,0,:,:MaturityIndex])
            
            # get the receive leg
            if self.RecLegCcy == 'GBP':
                RecGBPNot = self.RecLegNotional * np.ones(SimShape)
                #* np.exp(-MaturityIndex/365*DF[BatchIndex, RecCcyIndex,:,MaturityIndex])
            else:
                RecCcyIndex = CcyList.index(self.RecLegCcy)
                RecGBPNot = self.RecLegNotional/Sims[BatchIndex,RecCcyIndex,:,:MaturityIndex] #* np.exp(-MaturityIndex/365*DF[BatchIndex, RecCcyIndex,:,:MaturityIndex])
            
            # get the pay leg
            if self.PayLegCcy == 'GBP':
                PayGBPNot = self.PayLegNotional * np.ones(SimShape)
                #* np.exp(-MaturityIndex/365*DF[BatchIndex, RecPayIndex,:,MaturityIndex])
            else:
                PayCcyIndex = CcyList.index(self.PayLegCcy)
                PayGBPNot = self.PayLegNotional/Sims[BatchIndex,PayCcyIndex,0,0]*np.ones(SimShape)
                #* np.exp(-MaturityIndex/365*DF[BatchIndex, PayCcyIndex,:,:MaturityIndex]
            # price the forward or spot from RecGBPNot and PayGBPNot (both are numpy array 1000 x days to maturity)
            self.MTF = RecGBPNot - PayGBPNot

    def MTM(self):
        if self.MTF is not None:
            return np.average(self.MTF[:,0])

    def EE(self):
        if self.MTF is not None:
            E = self.MTF[:,:]
            E[E < 0] = 0
            return np.mean(E, axis=0)
        
    def PFE(self,Percent):
        if self.MTF is not None:
            return np.percentile(self.MTF[:,:],Percent,axis=0,interpolation='nearest')

# Generate FX Sims    
[FXSims,FXCcyList,dfDates] = SimulateFXRates(Path + 'FX-TimeSeries-Mod.csv',startDate,endDate,NbSims,SimLength)

## Generate a trade
TradeStartDate = datetime.date(2015,6,1)
#FXRecIndex = dfDates.index[dfDates['DATE'] == TradeStartDate].tolist()[0] - dfDates.index[dfDates['DATE'] == startDate].tolist()[0]
#FXRecRate = FXSims[FXRecIndex,FXCcyList.index('EUR'),0,0]
#FXPayIndex = dfDates.index[dfDates['DATE'] == datetime.date(2015,6,1)].tolist()[0] - dfDates.index[dfDates['DATE'] == startDate].tolist()[0]
#FXPayRate = FXSims[FXPayIndex,FXCcyList.index('USD'),0,0]
a = FXfwdTrade(TradeStartDate,datetime.date(2016,1,2), 1000,'EUR',1100,'USD')


# plot initial PFEs vs realised MTM
a.GenerateMTF(datetime.date(2015,6,1),dfDates,FXCcyList,FXSims)
plt.clf()
MTMVector = []
for i in range(0,len(a.MTF[:,0])):
    #plt.plot(a.EE())
    plt.plot(a.PFE(98))
    plt.plot(a.PFE(90))
    plt.plot(a.PFE(75))
    plt.plot(a.PFE(25))
    plt.plot(a.PFE(10))
    plt.plot(a.PFE(2))
    
for BatchDate in daterange(a.TradeStartDate, a.maturityDate):
    a.GenerateMTF(BatchDate,dfDates,FXCcyList,FXSims)
    MTMVector.append(a.MTM())
plt.plot(MTMVector)
plt.show()

# Collat trade run chart
plt.clf()
PFE99 = []
PFE01 = []
MTMVector = []

a.GenerateMTF(TradeStartDate,dfDates,FXCcyList,FXSims)
for BatchDate in daterange(a.TradeStartDate, a.maturityDate):
    if (a.maturityDate-BatchDate).days >= 5:
        PFE99.append(a.PFE(99)[4])
        PFE01.append(a.PFE(1)[4])
        a.GenerateMTF(BatchDate,dfDates,FXCcyList,FXSims)
        MTMVector.append(a.MTM())
        
plt.plot(MTMVector)
plt.plot(PFE99)
plt.plot(PFE01)
plt.show()


#print(MTMVector)