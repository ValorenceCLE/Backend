import speedtest

st = speedtest.Speedtest()

st.download()
st.upload()
result = st.results.dict()
print(result)